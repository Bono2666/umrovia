"""S03 — tenant resolver, RBAC, workspace switch, isolasi antar-tenant (M1).

Exit gate Roadmap S03: "Cross-tenant access denied".
"""
import pytest
from django.db import connection

from modules.identity.models import User
from modules.tenants.models import MembershipStatus, Role, TenantMembership


def _csrf(client) -> str:
    token = client.get("/api/v1/auth/csrf").json()["csrfToken"]
    return token


def _add_member(db, user, tenant, role_name: str, perms: list) -> TenantMembership:
    role = Role.objects.create(tenant=tenant, name=role_name, permissions_json=perms)
    return TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant, user=user, role=role, status=MembershipStatus.ACTIVE
    )


# ------------------------------------------------------------------- switch --


@pytest.mark.django_db
def test_switch_workspace_success(client, user, owner_a, tenant_a):
    client.force_login(user)
    response = client.post(
        "/api/v1/workspaces/switch",
        {"slug": "travel-a"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=_csrf(client),
    )
    assert response.status_code == 200
    active = response.json()["active"]
    assert active["tenant"]["slug"] == "travel-a"
    assert active["role"] == "Owner"
    assert active["permissions"] == ["*"]
    assert client.session["active_tenant_slug"] == "travel-a"


@pytest.mark.django_db
def test_switch_to_non_member_tenant_denied(client, user, owner_a, tenant_b):
    client.force_login(user)
    response = client.post(
        "/api/v1/workspaces/switch",
        {"slug": "travel-b"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=_csrf(client),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "TENANT_ACCESS_DENIED"
    assert "active_tenant_slug" not in client.session


@pytest.mark.django_db
def test_switch_unknown_slug_same_denial(client, user, owner_a):
    """Slug tak dikenal → kode sama (tanpa oracle enumerasi tenant)."""
    client.force_login(user)
    response = client.post(
        "/api/v1/workspaces/switch",
        {"slug": "tidak-ada"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=_csrf(client),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "TENANT_ACCESS_DENIED"


# ------------------------------------------------------------------ resolver --


@pytest.mark.django_db
def test_host_subdomain_resolves_tenant(client, user, owner_a, settings):
    """Subdomain host `<slug>.localhost` = identitas tenant (§2.2)."""
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "travel-a.localhost"]
    client.force_login(user)
    response = client.get("/api/v1/memberships", HTTP_HOST="travel-a.localhost")
    assert response.status_code == 200
    assert response.json()["results"][0]["user"]["email"] == "owner@example.com"


@pytest.mark.django_db
def test_service_hosts_are_not_tenant_slugs(client, user, owner_a, settings):
    """`api.umrovia.com` (host API produksi) bukan workspace "api": resolusi lanjut ke
    sesi/membership, bukan context kosong yang menolak semua endpoint tenant."""
    from modules.tenants.resolver import slug_from_host

    assert [slug_from_host(h) for h in ("api.umrovia.com", "app.umrovia.com:443", "admin.umrovia.com", "travel-a.umrovia.com")] == [None, None, None, "travel-a"]
    settings.ALLOWED_HOSTS = [*settings.ALLOWED_HOSTS, "api.umrovia.com"]
    client.force_login(user)
    response = client.get("/api/v1/memberships", HTTP_HOST="api.umrovia.com")
    assert response.status_code == 200
    assert client.get("/api/v1/branches/mine", HTTP_HOST="api.umrovia.com").status_code == 200


@pytest.mark.django_db
def test_host_subdomain_without_membership_fails_closed(
    client, user, owner_a, tenant_b, settings
):
    """Host menunjuk tenant lain dan user bukan anggota → context kosong,
    TIDAK fallback diam-diam ke tenant sendiri (anti cross-tenant leak)."""
    settings.ALLOWED_HOSTS = [
        *settings.ALLOWED_HOSTS,
        "travel-a.localhost",
        "travel-b.localhost",
    ]
    client.force_login(user)
    response = client.get("/api/v1/memberships", HTTP_HOST="travel-b.localhost")
    assert response.status_code == 403
    assert response.json()["code"] == "TENANT_CONTEXT_REQUIRED"
    mine = client.get("/api/v1/branches/mine", HTTP_HOST="travel-b.localhost")
    assert mine.status_code == 403  # bukan 500 TenantContextMissingError


@pytest.mark.django_db
def test_session_switch_drives_context(client, db, user, owner_a, tenant_a, tenant_b):
    """Sesi switch dipakai bila tanpa subdomain: konteks pindah sesuai pilihan."""
    other_role = _add_member(db, user, tenant_b, "Sales", ["bookings.read"])
    client.force_login(user)

    # default (tanpa switch) = membership pertama → tenant A (Owner, grant penuh)
    assert client.get("/api/v1/memberships").status_code == 200

    csrf = _csrf(client)
    switch_b = client.post(
        "/api/v1/workspaces/switch",
        {"slug": "travel-b"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert switch_b.status_code == 200

    # konteks = tenant B, role Sales tanpa `memberships.read` → ditolak
    denied = client.get("/api/v1/memberships")
    assert denied.status_code == 403
    assert denied.json()["code"] == "permission_denied"

    # kembali ke tenant A → diizinkan lagi
    back = client.post(
        "/api/v1/workspaces/switch",
        {"slug": "travel-a"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert back.status_code == 200
    assert client.get("/api/v1/memberships").status_code == 200
    assert other_role.pk


# ---------------------------------------------------------------------- RBAC --


@pytest.mark.django_db
def test_memberships_list_scoped_to_own_tenant(client, user, owner_a, tenant_a, tenant_b, db):
    intruder = User.objects.create_user(email="intruder@travelb.id", password="x-pass-123")
    _add_member(db, intruder, tenant_b, "Owner", ["*"])

    client.force_login(user)
    response = client.get("/api/v1/memberships")
    assert response.status_code == 200
    emails = {row["user"]["email"] for row in response.json()["results"]}
    assert emails == {"owner@example.com"}  # anggota tenant B tak terlihat


@pytest.mark.django_db
def test_memberships_denied_without_grant(client, db, tenant_a):
    staff = User.objects.create_user(email="sales@travela.id", password="x-pass-123")
    _add_member(db, staff, tenant_a, "Sales", ["bookings.read"])
    client.force_login(staff)
    response = client.get("/api/v1/memberships")
    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


@pytest.mark.django_db
def test_memberships_requires_tenant_context(client, verified_user):
    """User tanpa membership → TENANT_CONTEXT_REQUIRED (fail-closed, §8.9)."""
    client.force_login(verified_user)
    response = client.get("/api/v1/memberships")
    assert response.status_code == 403
    assert response.json()["code"] == "TENANT_CONTEXT_REQUIRED"


@pytest.mark.django_db
def test_memberships_anonymous_denied(client, db):
    response = client.get("/api/v1/memberships")
    assert response.status_code == 403
    assert response.json()["code"] == "not_authenticated"


@pytest.mark.django_db
def test_me_includes_effective_permissions(client, user, owner_a):
    client.force_login(user)
    body = client.get("/api/v1/me").json()
    assert body["memberships"][0]["permissions"] == ["*"]


@pytest.mark.django_db
def test_me_reports_active_tenant_slug(client, user, owner_a, tenant_a, tenant_b):
    """`active_tenant_slug` = sesi switch; null = fallback membership pertama (S06)."""
    from modules.tenants.models import MembershipStatus, Role, TenantMembership

    client.force_login(user)
    assert client.get("/api/v1/me").json()["active_tenant_slug"] is None

    other_role = Role.objects.create(tenant=tenant_b, name="Sales", permissions_json=["bookings.read"])
    TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant_b, user=user, role=other_role, status=MembershipStatus.ACTIVE
    )
    csrf = _csrf(client)
    switched = client.post(
        "/api/v1/workspaces/switch",
        {"slug": tenant_b.slug},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert switched.status_code == 200
    assert client.get("/api/v1/me").json()["active_tenant_slug"] == tenant_b.slug


# ------------------------------------------------------- konteks & kebocoran --


@pytest.mark.django_db(transaction=True)
def test_tenant_setting_cleared_after_request(client, user, owner_a):
    """SET LOCAL app.tenant_id tidak bocor ke request berikutnya (§2.2)."""
    client.force_login(user)
    assert client.get("/api/v1/me").status_code == 200
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.tenant_id', true)")
        value = cursor.fetchone()[0]
    assert value in ("", None), f"konteks tenant bocor ke request berikutnya: {value!r}"
