"""S07 — Master jamaah + dokumen secured (exit gate: "CRUD, duplicate handling,
isolation"; Spec §5.2, §8.3, §10.1, §2.2, PRD MOD-04).

Membuktikan:
- CRUD jamaah: kode auto, normalisasi telepon, duplikat identitas DITANDAI
  (possible_duplicate_of) bukan digabung otomatis (MOD-04);
- NIK/paspor terenkripsi saat disimpan (nilai asli tak pernah ada di DB/resp/audit)
  dan hanya varian masked yang keluar API (§10.1);
- isolasi: list scoped, IDOR lintas-tenant → 404, RLS ENABLE+FORCE + policy
  NULLIF fail-closed pada kedua tabel (§5.6);
- matriks RBAC pilgrims.read/.write (§3): Sales tulis, Finance/DokReviewer baca;
- guard environment: trial → demo; pasca-konversi demo READ_ONLY ditolak,
  write pindah production (§2.2);
- dokumen: object_key wajib ber-prefix tenant/environment, versi naik otomatis,
  UNIQUE(pilgrim,kind,version), review approve/reject dengan alasan wajib (UI-11).
"""
from contextlib import contextmanager

import pytest
from django.db import connection
from django.utils import timezone

from modules.audit.models import AuditEvent
from modules.identity.models import User, UserStatus
from modules.pilgrims.crypto import decrypt_pii
from modules.pilgrims.models import Pilgrim, PilgrimDocument
from modules.tenants.context import clear_current_tenant, set_current_tenant
from modules.tenants.models import (
    Environment,
    EnvironmentState,
    MembershipStatus,
    Role,
    TenantEnvironment,
    TenantMembership,
)


@contextmanager
def _as_tenant(tenant):
    """Context tenant buatan test untuk seeding via ORM (jalur bypass sah)."""
    token = set_current_tenant(tenant)
    try:
        yield
    finally:
        clear_current_tenant(token)


def _csrf(client) -> str:
    return client.get("/api/v1/auth/csrf").json()["csrfToken"]


def _seed_env(tenant, environment: str = Environment.DEMO, state: str = EnvironmentState.ACTIVE):
    return TenantEnvironment.objects.create(tenant=tenant, environment=environment, state=state)


def _make_member(client, email: str, tenant, role_name: str, perms: list) -> User:
    member = User.objects.create_user(email=email, password="rahasia123")
    member.status = UserStatus.ACTIVE
    member.email_verified_at = timezone.now()
    member.save()
    TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant,
        user=member,
        role=Role.objects.create(tenant=tenant, name=role_name, permissions_json=perms),
        status=MembershipStatus.ACTIVE,
    )
    client.force_login(member)
    return member


NIK = "3175092102900001"
NIK_B = "3175092102900002"


# ------------------------------------------------------------------- CRUD --


@pytest.mark.django_db
def test_create_pilgrim_encrypts_identity_and_masks_output(auth_client, tenant_a):
    _seed_env(tenant_a)
    csrf = _csrf(auth_client)
    response = auth_client.post(
        "/api/v1/pilgrims",
        {
            "name": "Budi Santoso",
            "gender": "male",
            "birth_date": "1990-02-21",
            "birth_place": "Jakarta",
            "phone": "08123456789",
            "email": "budi@example.com",
            "identity_number": NIK,
            "passport_number": "c1234567",
        },
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 201, response.content
    payload = response.json()
    assert payload["code"].startswith("JM-")
    assert payload["environment"] == Environment.DEMO  # trial → demo (server-side)
    assert payload["identity_masked"] == "*" * 12 + NIK[-4:]
    assert payload["passport_masked"] == "*" * 4 + "4567"
    assert payload["phone"] == "+628123456789"  # kanonis E.164 §10.1
    assert NIK not in str(response.content)  # nilai asli tak pernah keluar
    assert "C1234567" not in str(response.content)
    assert "identity_number" not in payload  # write-only

    stored = Pilgrim.objects.without_tenant_guard().get(pk=payload["id"])
    assert NIK not in stored.identity_encrypted  # terenkripsi, bukan plaintext
    assert decrypt_pii(stored.identity_encrypted) == NIK
    assert decrypt_pii(stored.passport_encrypted) == "C1234567"
    assert stored.identity_hash  # hash dedup terisi

    event = AuditEvent.objects.get(action="pilgrims.created", tenant=tenant_a)
    assert NIK not in str(event.changes_json)


@pytest.mark.django_db
def test_pilgrim_validation_rejects_bad_input(auth_client, tenant_a):
    _seed_env(tenant_a)
    csrf = _csrf(auth_client)
    bad_nik = auth_client.post(
        "/api/v1/pilgrims",
        {"name": "X", "identity_number": "12345"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert bad_nik.status_code == 400
    bad_email = auth_client.post(
        "/api/v1/pilgrims",
        {"name": "X", "email": "bukan-email"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert bad_email.status_code == 400
    future_birth = auth_client.post(
        "/api/v1/pilgrims",
        {"name": "X", "birth_date": "2999-01-01"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert future_birth.status_code == 400


@pytest.mark.django_db
def test_duplicate_identity_flagged_not_merged(auth_client, tenant_a):
    _seed_env(tenant_a)
    csrf = _csrf(auth_client)
    first = auth_client.post(
        "/api/v1/pilgrims",
        {"name": "Budi Santoso", "identity_number": NIK},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    ).json()
    # NIK sama dengan format berbeda (spasi/dash) → tetap terdeteksi
    second = auth_client.post(
        "/api/v1/pilgrims",
        {"name": "B. Santoso", "identity_number": f" {NIK[:6]}-{NIK[6:]} "},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert second.status_code == 201  # BOLEH dibuat — ditandai, bukan digabung
    second_payload = second.json()
    assert second_payload["possible_duplicate_of"] == first["id"]
    assert Pilgrim.objects.without_tenant_guard().count() == 2  # tidak ada merge

    # identitas berbeda → tanpa tanda
    distinct = auth_client.post(
        "/api/v1/pilgrims",
        {"name": "Citra", "identity_number": NIK_B},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    ).json()
    assert distinct["possible_duplicate_of"] is None


@pytest.mark.django_db
def test_pilgrim_search_and_list_scoped(auth_client, tenant_a, tenant_b):
    _seed_env(tenant_a)
    _seed_env(tenant_b)
    csrf = _csrf(auth_client)
    auth_client.post(
        "/api/v1/pilgrims",
        {"name": "Budi Santoso", "identity_number": NIK, "phone": "08123456789"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    # seed jamaah tenant_b langsung via ORM dengan context tenant (manager scoped)
    with _as_tenant(tenant_b):
        Pilgrim.objects.create(
            tenant=tenant_b, environment=Environment.DEMO, code="JM-F0REIGN1", name="Foreign"
        )

    listed = auth_client.get("/api/v1/pilgrims")
    assert listed.status_code == 200
    assert [r["name"] for r in listed.json()["results"]] == ["Budi Santoso"]

    by_name = auth_client.get("/api/v1/pilgrims?q=budi").json()["results"]
    assert len(by_name) == 1
    # pencarian NIK exact via hash aman (§5.2 search normalisasi)
    by_nik = auth_client.get(f"/api/v1/pilgrims?q={NIK}").json()["results"]
    assert len(by_nik) == 1 and by_nik[0]["name"] == "Budi Santoso"


# ------------------------------------------------------------------ RBAC --


@pytest.mark.django_db
def test_rbac_matrix_pilgrims(client, db, user, owner_a, tenant_a):
    _seed_env(tenant_a)
    sales = _make_member(client, "sales@example.com", tenant_a, "Sales", ["pilgrims.read", "pilgrims.write"])
    assert sales.is_authenticated
    csrf = _csrf(client)
    created = client.post(
        "/api/v1/pilgrims",
        {"name": "Pelanggan Sales"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert created.status_code == 201  # CS/Pendaftaran boleh daftarkan jamaah (PRD)

    finance = _make_member(client, "finance2@example.com", tenant_a, "Finance", ["pilgrims.read"])
    assert finance.is_authenticated
    assert client.get("/api/v1/pilgrims").status_code == 200  # baca OK
    denied = client.post(
        "/api/v1/pilgrims",
        {"name": "Tolak"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert denied.status_code == 403  # Finance tanpa tulis

    _make_member(client, "ops@example.com", tenant_a, "Operations", [])  # tanpa pilgrims.*
    assert client.get("/api/v1/pilgrims").status_code == 403


@pytest.mark.django_db
def test_pilgrim_cross_tenant_idor_404(auth_client, tenant_a, tenant_b):
    _seed_env(tenant_a)
    with _as_tenant(tenant_b):
        foreign = Pilgrim.objects.create(
            tenant=tenant_b, environment=Environment.DEMO, code="JM-FOREIGN1", name="Foreign"
        )
    assert auth_client.get(f"/api/v1/pilgrims/{foreign.pk}").status_code == 404
    csrf = _csrf(auth_client)
    patched = auth_client.patch(
        f"/api/v1/pilgrims/{foreign.pk}",
        {"name": "Hack"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert patched.status_code == 404


# ------------------------------------------------------------- RLS (§5.6) --


@pytest.mark.django_db
@pytest.mark.parametrize("table", ["pilgrims_pilgrim", "pilgrims_pilgrimdocument"])
def test_pilgrim_tables_have_enforced_rls_policy(db, table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s",
            [table],
        )
        assert cursor.fetchone() == (True, True), f"{table} harus ENABLE+FORCE RLS (ADR-0003 §3)"
        cursor.execute(
            "SELECT qual, with_check FROM pg_policies WHERE tablename = %s", [table]
        )
        policy = cursor.fetchone()
        assert policy is not None
        for clause in policy:
            assert "current_setting('app.tenant_id'" in clause
            assert "NULLIF" in clause  # konteks kosong → NULL → deny (fail-closed)


# ------------------------------------------------------ environment guard --


@pytest.mark.django_db
def test_write_moves_to_production_after_conversion(auth_client, tenant_a):
    _seed_env(tenant_a, Environment.DEMO, EnvironmentState.READ_ONLY)  # pasca-konversi
    prod = _seed_env(tenant_a, Environment.PRODUCTION, EnvironmentState.ACTIVE)
    assert prod.environment == Environment.PRODUCTION

    with _as_tenant(tenant_a):
        demo_pilgrim = Pilgrim.objects.create(
            tenant=tenant_a, environment=Environment.DEMO, code="JM-DEMO001", name="Jamaah Demo"
        )

    csrf = _csrf(auth_client)
    created = auth_client.post(
        "/api/v1/pilgrims",
        {"name": "Produksi Baru"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert created.status_code == 201
    assert created.json()["environment"] == Environment.PRODUCTION  # pindah namespace

    # jamaah demo (READ_ONLY) tak bisa diubah — §2.2 akses demo read-only
    patched = auth_client.patch(
        f"/api/v1/pilgrims/{demo_pilgrim.pk}",
        {"name": "Ubah Demo"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert patched.status_code == 403
    # tetap terbaca
    assert auth_client.get(f"/api/v1/pilgrims/{demo_pilgrim.pk}").status_code == 200


# --------------------------------------------------------------- dokumen --


def _register_document(client, pilgrim_id, csrf, kind="passport", key_tail="doc.pdf"):
    pilgrim = Pilgrim.objects.without_tenant_guard().get(pk=pilgrim_id)
    object_key = f"tenants/{pilgrim.tenant_id}/environments/{pilgrim.environment}/pilgrims/{pilgrim.id}/{kind}/{key_tail}"
    return client.post(
        f"/api/v1/pilgrims/{pilgrim_id}/documents",
        {"kind": kind, "object_key": object_key},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


@pytest.mark.django_db
def test_document_object_key_prefix_enforced_and_version_increments(auth_client, tenant_a):
    _seed_env(tenant_a)
    csrf = _csrf(auth_client)
    pilgrim = auth_client.post(
        "/api/v1/pilgrims", {"name": "Aminah"}, content_type="application/json", HTTP_X_CSRFTOKEN=csrf
    ).json()

    evil = auth_client.post(
        f"/api/v1/pilgrims/{pilgrim['id']}/documents",
        {"kind": "ktp", "object_key": "tenants/00000000-0000-0000-0000-000000000000/environments/demo/pilgrims/x/ktp/x.pdf"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert evil.status_code == 400  # prefix tenant/environment wajib (§5.2)

    first = _register_document(auth_client, pilgrim["id"], csrf, kind="passport")
    assert first.status_code == 201 and first.json()["version"] == 1
    second = _register_document(auth_client, pilgrim["id"], csrf, kind="passport", key_tail="doc2.pdf")
    assert second.json()["version"] == 2  # versi naik otomatis

    # UNIQUE(pilgrim, kind, version) — constraint ada di schema
    assert PilgrimDocument.objects.without_tenant_guard().filter(pilgrim__pk=pilgrim["id"]).count() == 2


@pytest.mark.django_db
def test_document_review_requires_reason_on_reject(client, db, user, owner_a, tenant_a):
    _seed_env(tenant_a)
    client.force_login(user)
    csrf = _csrf(client)
    pilgrim = client.post(
        "/api/v1/pilgrims", {"name": "Aminah"}, content_type="application/json", HTTP_X_CSRFTOKEN=csrf
    ).json()
    doc = _register_document(client, pilgrim["id"], csrf).json()

    reviewer = _make_member(
        client, "reviewer@example.com", tenant_a, "Document Reviewer", ["documents.review", "pilgrims.read"]
    )
    csrf = _csrf(client)
    no_reason = client.patch(
        f"/api/v1/pilgrims/{pilgrim['id']}/documents/{doc['id']}",
        {"status": "REJECTED"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert no_reason.status_code == 400  # alasan wajib saat reject (UI-11)

    rejected = client.patch(
        f"/api/v1/pilgrims/{pilgrim['id']}/documents/{doc['id']}",
        {"status": "REJECTED", "reason": "Foto buram"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert rejected.status_code == 200
    body = rejected.json()
    assert body["status"] == "REJECTED" and body["reason"] == "Foto buram"
    assert body["reviewed_by"] == str(reviewer.pk)

    # Sales (tanpa documents.review) tak boleh review
    _make_member(client, "sales2@example.com", tenant_a, "Sales", ["pilgrims.read", "pilgrims.write"])
    csrf = _csrf(client)
    denied = client.patch(
        f"/api/v1/pilgrims/{pilgrim['id']}/documents/{doc['id']}",
        {"status": "APPROVED"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert denied.status_code == 403

    event = AuditEvent.objects.filter(action="pilgrim_documents.reviewed").first()
    assert event is not None and event.changes_json["status"] == "REJECTED"
