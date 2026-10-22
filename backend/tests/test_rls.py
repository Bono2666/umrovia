"""S03 — PostgreSQL RLS: fail-closed tanpa konteks + isolasi lintas-tenant (§5.6).

Membuktikan mekanisme `common.rls` pada tabel probe (tabel bisnis nyata mulai
S05+ memakai helper yang sama di migrasinya). Karena superuser selalu bypass
RLS, test memindahkan sesi ke role non-superuser bila DB user superuser.
"""
from contextlib import contextmanager

import pytest
from django.db import DatabaseError, connection, transaction

from common.rls import disable_tenant_rls_statements, tenant_rls_statements

PROBE = "s03_rls_probe"
PROBE_ROLE = "s03_rls_probe_role"


def _is_superuser() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        return bool(cursor.fetchone()[0])


def _set_tenant(tenant_id: str | None) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, TRUE)", [tenant_id or ""])


def _insert(tenant_id: str, label: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO s03_rls_probe (tenant_id, label) VALUES (%s, %s)",
            [tenant_id, label],
        )


def _labels() -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT label FROM s03_rls_probe ORDER BY label")
        return [row[0] for row in cursor.fetchall()]


@contextmanager
def _probe_table():
    """Buat tabel probe + policy RLS; bersih otomatis (transaksi test rollback)."""
    with connection.schema_editor() as editor:
        editor.execute(f"CREATE TABLE {PROBE} (tenant_id uuid NOT NULL, label TEXT NOT NULL)")
    with connection.cursor() as cursor:
        for statement in tenant_rls_statements(PROBE):
            cursor.execute(statement)
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"DROP TABLE IF EXISTS {PROBE}")


@contextmanager
def _as_bypass_owner():
    """Superuser harus pindah role — RLS baru berlaku untuk non-superuser."""
    if not _is_superuser():
        yield False  # owner non-superuser: FORCE ROW LEVEL SECURITY sudah menjamin
        return
    with connection.cursor() as cursor:
        cursor.execute(f"DROP ROLE IF EXISTS {PROBE_ROLE}")
        cursor.execute(f"CREATE ROLE {PROBE_ROLE} NOLOGIN")
        cursor.execute(f"GRANT ALL ON TABLE {PROBE} TO {PROBE_ROLE}")
        cursor.execute(f"SET ROLE {PROBE_ROLE}")
    try:
        yield True
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")


@pytest.mark.django_db
def test_rls_fail_closed_and_cross_tenant_isolation(db, tenant_a, tenant_b):
    a_id, b_id = str(tenant_a.id), str(tenant_b.id)
    with _probe_table():
        # seed sebagai owner — di bawah konteks masing-masing tenant
        _set_tenant(a_id)
        _insert(a_id, "A1")
        _set_tenant(b_id)
        _insert(b_id, "B1")

        with _as_bypass_owner() as _role_switched:
            # 1) konteks tenant A → hanya baris A yang terlihat (USING)
            _set_tenant(a_id)
            assert _labels() == ["A1"], "baris tenant B bocor ke context A"

            # 2) WITH CHECK: insert baris tenant B di bawah context A → ditolak
            with pytest.raises(DatabaseError) as exc, transaction.atomic():
                _insert(b_id, "B2")
            assert "row-level security" in str(exc.value).lower()

            # 3) fail-closed: tanpa konteks → tidak ada baris sama sekali
            _set_tenant("")
            assert _labels() == [], "RLS tidak fail-closed tanpa konteks tenant"

            # 4) konteks tenant B → hanya baris B (query write/read normal)
            _set_tenant(b_id)
            assert _labels() == ["B1"]


@pytest.mark.django_db
def test_rls_statements_follow_spec_pattern():
    statements = tenant_rls_statements("bookings")
    joined = "\n".join(statements)
    assert "ENABLE ROW LEVEL SECURITY" in joined
    assert "FORCE ROW LEVEL SECURITY" in joined
    assert "current_setting('app.tenant_id', true)" in joined
    assert "NULLIF" in joined  # konteks kosong → NULL → deny (fail-closed)
    assert "WITH CHECK" in joined
    disable = "\n".join(disable_tenant_rls_statements("bookings"))
    assert "DROP POLICY" in disable and "DISABLE ROW LEVEL SECURITY" in disable


@pytest.mark.django_db
def test_rls_rejects_unsafe_identifiers():
    from common.rls import _check_identifier

    with pytest.raises(ValueError):
        tenant_rls_statements('bookings; DROP TABLE users')
    with pytest.raises(ValueError):
        _check_identifier("Bookings")
