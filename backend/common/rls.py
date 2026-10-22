"""PostgreSQL Row Level Security — helper penerapan pola Spec §5.6.

Setiap TABEL BISNIS berkolom `tenant_id` (Spec §5.2+) wajib diaktifkan RLS-nya
lewat helper ini di migrasi tabel bersangkutan, dengan pola:

    ALTER TABLE x ENABLE ROW LEVEL SECURITY;
    ALTER TABLE x FORCE ROW LEVEL SECURITY;   -- berlaku juga untuk table owner
    CREATE POLICY tenant_scope_x ON x
      USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
      WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)

`NULLIF(..., '')` memastikan konteks kosong/tanpa set → NULL → baris tak pernah
cocok → DENY (fail-closed), alih-alih error casting uuid. `FORCE` membuat policy
berlaku pula bagi owner tabel; superuser tetap bypass (PostgreSQL) — karena itu
test memakai role non-superuser (lihat tests/test_rls.py).

Tabel kontrol-plane (identity/tenancy §5.1: users, tenants, roles, memberships,
trial) TIDAK di-RLS-kan: dibutuhkan sebelum context ada (resolusi membership)
dan bersifat lintas-tenant by design — dijaga lapis scope ORM + otorisasi endpoint
(ADR-0003).
"""
import re

from django.db import connection

_IDENTIFIER_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _check_identifier(name: str) -> str:
    if not _IDENTIFIER_RE.match(name):
        raise ValueError(f"Identifier SQL tidak valid: {name!r}")
    return name


def tenant_rls_statements(table: str) -> list[str]:
    """Statement SQL (urut) untuk mengaktifkan RLS fail-closed pada `table`."""
    table = _check_identifier(table)
    ctx = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS tenant_scope_{table} ON {table}",
        f"CREATE POLICY tenant_scope_{table} ON {table}"
        f" USING (tenant_id = {ctx}) WITH CHECK (tenant_id = {ctx})",
    ]


def disable_tenant_rls_statements(table: str) -> list[str]:
    table = _check_identifier(table)
    return [
        f"DROP POLICY IF EXISTS tenant_scope_{table} ON {table}",
        f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
    ]


def enable_tenant_rls(table: str) -> None:
    """Jalankan penerapan RLS (dipakai di migrasi tabel bisnis)."""
    with connection.cursor() as cursor:
        for statement in tenant_rls_statements(table):
            cursor.execute(statement)
