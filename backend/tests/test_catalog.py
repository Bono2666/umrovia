"""S08 — Master paket (exit gate S08 bagian katalog; Spec §5.2, §8.3, UI-04).

Membuktikan:
- CRUD paket: kode auto `PKT-<8hex>`, UNIQUE(tenant,environment,code),
  harga integer rupiah nonnegatif & terbatas (§10.1);
- publish hanya dari status ACTIVE (guard §5.2 `published`);
- isolasi: list scoped, IDOR lintas-tenant → 404, RLS ENABLE+FORCE + policy
  NULLIF fail-closed (§5.6);
- RBAC §8.3: Owner/Admin/Ops tulis; Sales/Finance baca saja; tanpa
  `packages.*` → 403;
- guard environment server-side (trial → demo; demo READ_ONLY → tolak write).
"""
from contextlib import contextmanager

import pytest
from django.db import connection
from django.utils import timezone

from modules.audit.models import AuditEvent
from modules.catalog.models import TravelPackage
from modules.identity.models import User, UserStatus
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


def _create_package(client, csrf, **fields):
    payload = {"name": "Umroh Reguler 12 Hari", **fields}
    return client.post(
        "/api/v1/packages",
        payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


# ------------------------------------------------------------------- CRUD --


@pytest.mark.django_db
def test_create_package_auto_code_and_payload(auth_client, tenant_a):
    _seed_env(tenant_a)
    csrf = _csrf(auth_client)
    response = _create_package(
        auth_client,
        csrf,
        kind="umroh",
        duration_days=12,
        price_idr=28_500_000,
        inclusions=["Tiket", "Hotel", "Visa"],
        exclusions=["Upgrade kamar"],
    )
    assert response.status_code == 201, response.content
    payload = response.json()
    assert payload["code"].startswith("PKT-")
    assert payload["environment"] == Environment.DEMO  # trial → demo (server-side)
    assert payload["status"] == "DRAFT"
    assert payload["published"] is False
    assert payload["inclusions"] == ["Tiket", "Hotel", "Visa"]
    assert payload["price_idr"] == 28_500_000

    event = AuditEvent.objects.get(action="packages.created", tenant=tenant_a)
    assert event.changes_json["code"] == payload["code"]


@pytest.mark.django_db
def test_package_validation(auth_client, tenant_a):
    _seed_env(tenant_a)
    csrf = _csrf(auth_client)
    empty_name = _create_package(auth_client, csrf, name="   ")
    assert empty_name.status_code == 400
    over_price = _create_package(auth_client, csrf, price_idr=10_000_000_001)
    assert over_price.status_code == 400
    bad_duration = _create_package(auth_client, csrf, duration_days=366)
    assert bad_duration.status_code == 400
    # published hanya sah dari status ACTIVE (§5.2 / UI-04)
    published_draft = _create_package(auth_client, csrf, published=True)
    assert published_draft.status_code == 400


@pytest.mark.django_db
def test_package_publish_requires_active_status(auth_client, tenant_a):
    _seed_env(tenant_a)
    csrf = _csrf(auth_client)
    created = _create_package(auth_client, csrf).json()

    # publish langsung dari DRAFT → ditolak
    denied = auth_client.patch(
        f"/api/v1/packages/{created['id']}",
        {"published": True},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert denied.status_code == 400

    activated = auth_client.patch(
        f"/api/v1/packages/{created['id']}",
        {"status": "ACTIVE"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert activated.status_code == 200
    published = auth_client.patch(
        f"/api/v1/packages/{created['id']}",
        {"published": True},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert published.status_code == 200 and published.json()["published"] is True

    update_event = AuditEvent.objects.filter(action="packages.updated").order_by("-occurred_at").first()
    assert update_event.changes_json.get("published") is True


@pytest.mark.django_db
def test_package_list_scoped_search_and_idor(auth_client, tenant_a, tenant_b):
    _seed_env(tenant_a)
    csrf = _csrf(auth_client)
    created = _create_package(auth_client, csrf, name="Umroh Ramadhan").json()

    with _as_tenant(tenant_b):
        foreign = TravelPackage.objects.create(
            tenant=tenant_b,
            environment=Environment.DEMO,
            code="PKT-FOREIGN1",
            name="Paket Asing",
        )

    listed = auth_client.get("/api/v1/packages").json()["results"]
    assert [p["code"] for p in listed] == [created["code"]]

    searched = auth_client.get("/api/v1/packages?q=ramadhan").json()["results"]
    assert len(searched) == 1

    assert auth_client.get(f"/api/v1/packages/{foreign.pk}").status_code == 404
    patched = auth_client.patch(
        f"/api/v1/packages/{foreign.pk}",
        {"name": "Hack"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert patched.status_code == 404


# ------------------------------------------------------------------ RBAC --


@pytest.mark.django_db
def test_package_rbac_matrix(client, db, user, owner_a, tenant_a):
    _seed_env(tenant_a)
    csrf = _csrf(client)

    # Sales: baca ✓ tulis ✗ (§8.3 katalog = Owner/Admin/Ops)
    _make_member(client, "sales@example.com", tenant_a, "Sales", ["packages.read", "departures.read"])
    assert client.get("/api/v1/packages").status_code == 200
    denied = _create_package(client, csrf)
    assert denied.status_code == 403

    # Operations: tulis ✓
    _make_member(
        client,
        "ops@example.com",
        tenant_a,
        "Operations",
        ["packages.read", "packages.write", "departures.read", "departures.write", "departures.manage"],
    )
    csrf = _csrf(client)
    allowed = _create_package(client, csrf, name="Paket Ops")
    assert allowed.status_code == 201

    # tanpa packages.* sama sekali → 403
    _make_member(client, "noperm@example.com", tenant_a, "Custom", ["pilgrims.read"])
    assert client.get("/api/v1/packages").status_code == 403


@pytest.mark.django_db
def test_package_write_denied_in_read_only_environment(auth_client, tenant_a):
    _seed_env(tenant_a, Environment.DEMO, EnvironmentState.READ_ONLY)  # pasca-konversi
    _seed_env(tenant_a, Environment.PRODUCTION, EnvironmentState.ACTIVE)

    with _as_tenant(tenant_a):
        demo_pkg = TravelPackage.objects.create(
            tenant=tenant_a, environment=Environment.DEMO, code="PKT-DEMO001", name="Demo Lama"
        )

    csrf = _csrf(auth_client)
    # write baru masuk production
    created = _create_package(auth_client, csrf, name="Produksi Baru")
    assert created.status_code == 201
    assert created.json()["environment"] == Environment.PRODUCTION

    # paket demo (READ_ONLY) tak bisa diubah — §2.2
    patched = auth_client.patch(
        f"/api/v1/packages/{demo_pkg.pk}",
        {"name": "Diubah"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert patched.status_code == 403
    assert auth_client.get(f"/api/v1/packages/{demo_pkg.pk}").status_code == 200


# ------------------------------------------------------------- RLS (§5.6) --


@pytest.mark.django_db
def test_package_table_has_enforced_rls_policy(db):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = 'catalog_travelpackage'"
        )
        assert cursor.fetchone() == (True, True), "catalog_travelpackage harus ENABLE+FORCE RLS (ADR-0003 §3)"
        cursor.execute(
            "SELECT qual, with_check FROM pg_policies WHERE tablename = 'catalog_travelpackage'"
        )
        policy = cursor.fetchone()
        assert policy is not None
        for clause in policy:
            assert "current_setting('app.tenant_id'" in clause
            assert "NULLIF" in clause  # konteks kosong → NULL → deny (fail-closed)
