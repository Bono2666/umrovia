"""S05 — staff/invite, roles CRUD, tenant settings, rekening bank, audit (exit gate:
"RBAC and audit passes"; Spec §8.1, §5.1, §5.3, §5.5, matriks §3).

Membuktikan: guard IDOR lintas-tenant (404/400), guard Owner terakhir, matriks
RBAC (Owner/Admin/Sales/Finance), masking nomor rekening (asli tak pernah
tersimpan/dikirim), audit append-only ter-redact, hook INVITED→ACTIVE saat
verifikasi email.
"""
import re
from contextlib import contextmanager

import pytest
from django.db import connection
from django.utils import timezone

from modules.audit.models import AuditEvent
from modules.audit.services import redact
from modules.identity.models import User, UserStatus
from modules.tenants.models import MembershipStatus, Role, TenantMembership, TenantSettings
from modules.tenants.services import provision_workspace
from modules.travel_finance.models import TravelBankAccount, mask_account_number


def _csrf(client) -> str:
    return client.get("/api/v1/auth/csrf").json()["csrfToken"]


def _add_member(db, user, tenant, role_name: str, perms: list) -> TenantMembership:
    role = Role.objects.create(tenant=tenant, name=role_name, permissions_json=perms)
    return TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant, user=user, role=role, status=MembershipStatus.ACTIVE
    )


def _make_staff(db, tenant, email: str, role_name: str, perms: list):
    """Buat user ACTIVE + membership role tertentu di `tenant` → (user, role)."""
    staff = User.objects.create_user(email=email, password="rahasia123")
    staff.status = UserStatus.ACTIVE
    staff.email_verified_at = timezone.now()
    staff.save()
    role = Role.objects.create(tenant=tenant, name=role_name, permissions_json=perms)
    TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant, user=staff, role=role, status=MembershipStatus.ACTIVE
    )
    return staff, role


@contextmanager
def _tenant_ctx(tenant_id):
    """Set konteks RLS (SET LOCAL dalam transaksi test) untuk seeding langsung."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, TRUE)", [str(tenant_id)])
    yield


def _seed_bank(tenant, **kwargs) -> TravelBankAccount:
    defaults = {
        "bank_name": "BCA",
        "account_name": "PT Travel",
        "account_masked": "************1234",
    }
    defaults.update(kwargs)
    with _tenant_ctx(tenant.id):
        return TravelBankAccount.objects.without_tenant_guard().create(tenant=tenant, **defaults)


def _audit_actions() -> list[str]:
    return list(AuditEvent.objects.order_by().values_list("action", flat=True))


# ------------------------------------------------------------ tenant settings --


@pytest.mark.django_db
def test_settings_get_defaults_and_patch_persists(auth_client, owner_a, tenant_a):
    got = auth_client.get("/api/v1/tenant/settings")
    assert got.status_code == 200
    assert set(got.json()) == {"branding_json", "invoice_config_json", "rules_json"}
    assert got.json()["branding_json"] == {}

    csrf = _csrf(auth_client)
    patched = auth_client.patch(
        "/api/v1/tenant/settings",
        {"branding_json": {"primary_color": "#123456"}},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert patched.status_code == 200
    assert patched.json()["branding_json"] == {"primary_color": "#123456"}
    # bagian lain tidak ikut berubah (replace per-bagian)
    assert patched.json()["rules_json"] == {}

    again = auth_client.get("/api/v1/tenant/settings")
    assert again.json()["branding_json"] == {"primary_color": "#123456"}

    row = TenantSettings.objects.get(tenant=tenant_a)
    assert row.branding_json == {"primary_color": "#123456"}
    assert "tenant.settings.updated" in _audit_actions()


@pytest.mark.django_db
def test_settings_patch_as_admin_allowed(client, db, user, owner_a, tenant_a, verified_user):
    _add_member(db, verified_user, tenant_a, "Admin", ["tenant.settings.read", "tenant.settings.write"])
    client.force_login(verified_user)
    csrf = _csrf(client)
    response = client.patch(
        "/api/v1/tenant/settings",
        {"invoice_config_json": {"due_days": 7}},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 200
    assert response.json()["invoice_config_json"] == {"due_days": 7}


@pytest.mark.django_db
def test_settings_denied_for_sales(client, db, user, owner_a, tenant_a):
    sales, _ = _make_staff(db, tenant_a, "sales@example.com", "Sales", ["bookings.read"])
    client.force_login(sales)
    assert client.get("/api/v1/tenant/settings").status_code == 403
    csrf = _csrf(client)
    denied = client.patch(
        "/api/v1/tenant/settings",
        {"branding_json": {"x": 1}},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "permission_denied"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload_field,payload_value",
    [
        ("branding_json", ["not", "an", "object"]),
        ("rules_json", {"k": "x" * 20_000}),  # > 16 KiB
    ],
)
def test_settings_patch_rejects_invalid_payload(auth_client, owner_a, payload_field, payload_value):
    csrf = _csrf(auth_client)
    response = auth_client.patch(
        "/api/v1/tenant/settings",
        {payload_field: payload_value},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 400
    assert response.json()["field_errors"]


# ----------------------------------------------------------------- invitations --


@pytest.mark.django_db
def test_invite_new_staff_creates_pending_user_and_invited_membership(
    auth_client, db, tenant_a, owner_a
):
    sales_role = Role.objects.create(
        tenant=tenant_a, name="Sales", permissions_json=["bookings.read"]
    )
    csrf = _csrf(auth_client)
    response = auth_client.post(
        "/api/v1/memberships",
        {"email": "New.Staff@Example.com", "role_id": str(sales_role.id)},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 201
    row = response.json()["membership"]
    assert row["status"] == MembershipStatus.INVITED
    assert row["role"] == "Sales"
    assert row["role_id"] == str(sales_role.id)

    invited_user = User.objects.get(email="new.staff@example.com")
    assert invited_user.status == UserStatus.PENDING_VERIFICATION
    assert invited_user.has_usable_password() is False
    assert "memberships.invited" in _audit_actions()


@pytest.mark.django_db
def test_invite_existing_active_user_is_immediate(auth_client, db, tenant_a, owner_a, verified_user):
    csrf = _csrf(auth_client)
    response = auth_client.post(
        "/api/v1/memberships",
        {"email": verified_user.email, "role_id": str(Role.objects.create(tenant=tenant_a, name="Ops").id)},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 201
    assert response.json()["membership"]["status"] == MembershipStatus.ACTIVE


@pytest.mark.django_db
def test_invite_duplicate_membership_rejected(auth_client, db, tenant_a, owner_a):
    role = Role.objects.create(tenant=tenant_a, name="Sales")
    csrf = _csrf(auth_client)
    body = {"email": "dup@example.com", "role_id": str(role.id)}
    first = auth_client.post(
        "/api/v1/memberships", body, content_type="application/json", HTTP_X_CSRFTOKEN=csrf
    )
    assert first.status_code == 201
    second = auth_client.post(
        "/api/v1/memberships", body, content_type="application/json", HTTP_X_CSRFTOKEN=csrf
    )
    assert second.status_code == 400
    assert second.json()["field_errors"]["email"]


@pytest.mark.django_db
def test_invite_cross_tenant_role_rejected(auth_client, db, tenant_a, tenant_b, owner_a):
    foreign_role = Role.objects.create(tenant=tenant_b, name="SalesB")
    csrf = _csrf(auth_client)
    response = auth_client.post(
        "/api/v1/memberships",
        {"email": "x@example.com", "role_id": str(foreign_role.id)},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 400
    assert "role_id" in response.json()["field_errors"]
    # tidak ada anggota/pengguna yang terbuat
    assert not User.objects.filter(email="x@example.com").exists()


@pytest.mark.django_db
def test_invite_denied_for_sales_role(client, db, user, owner_a, tenant_a):
    sales, role = _make_staff(
        db, tenant_a, "sales2@example.com", "SalesOnly", ["bookings.create"]
    )
    client.force_login(sales)
    csrf = _csrf(client)
    denied = client.post(
        "/api/v1/memberships",
        {"email": "z@example.com", "role_id": str(role.id)},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "permission_denied"


@pytest.mark.django_db
def test_invited_staff_activates_on_email_verification(client, mailoutbox, db, tenant_a, owner_a):
    # dibuat lewat service langsung (konteks request tidak diperlukan)
    from modules.tenants.services import invite_member

    role = Role.objects.create(tenant=tenant_a, name="Sales", permissions_json=["bookings.read"])
    membership, created = invite_member(tenant=tenant_a, email="invitee@example.com", role=role)
    assert created and membership.status == MembershipStatus.INVITED

    # user pending → resend-verification menerbitkan token (jalur yang sama dengan register)
    resend = client.post(
        "/api/v1/auth/resend-verification",
        {"email": "invitee@example.com"},
        content_type="application/json",
    )
    assert resend.status_code == 200
    token = re.search(r"token=([A-Za-z0-9_\-]+)", mailoutbox[-1].body).group(1)

    verify = client.post(
        "/api/v1/auth/verify-email", {"token": token}, content_type="application/json"
    )
    assert verify.status_code == 200

    membership.refresh_from_db()
    assert membership.status == MembershipStatus.ACTIVE
    assert "memberships.activated" in _audit_actions()


# ------------------------------------------------------------ role & revoke --


@pytest.mark.django_db
def test_membership_role_change_owner_only(client, db, user, owner_a, tenant_a, verified_user):
    member = _add_member(db, verified_user, tenant_a, "Sales", ["bookings.read"])
    target_role = Role.objects.create(tenant=tenant_a, name="Finance", permissions_json=["invoices.read"])
    client.force_login(user)
    csrf = _csrf(client)
    response = client.patch(
        f"/api/v1/memberships/{member.id}",
        {"role_id": str(target_role.id)},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 200
    assert response.json()["membership"]["role"] == "Finance"
    assert "memberships.role_changed" in _audit_actions()


@pytest.mark.django_db
def test_membership_manage_denied_for_admin(client, db, user, tenant_a, owner_a):
    # Admin punya memberships.write tapi TIDAK memberships.manage (Owner-only §8.1)
    admin, _ = _make_staff(
        db, tenant_a, "admin@example.com", "Admin", ["memberships.read", "memberships.write"]
    )
    staff, sales_role = _make_staff(db, tenant_a, "staff@example.com", "Sales", ["bookings.read"])
    member = TenantMembership.objects.without_tenant_guard().get(
        tenant=tenant_a, user=staff, role=sales_role
    )
    client.force_login(admin)
    csrf = _csrf(client)
    new_role = Role.objects.create(tenant=tenant_a, name="Ops", permissions_json=[])
    denied = client.patch(
        f"/api/v1/memberships/{member.id}",
        {"role_id": str(new_role.id)},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert denied.status_code == 403
    denied_delete = client.delete(f"/api/v1/memberships/{member.id}", HTTP_X_CSRFTOKEN=csrf)
    assert denied_delete.status_code == 403


@pytest.mark.django_db
def test_last_owner_cannot_be_revoked_or_demoted(auth_client, client, db, user, owner_a, tenant_a):
    # owner_a = satu-satunya Owner aktif
    csrf = _csrf(auth_client)
    demote = auth_client.patch(
        f"/api/v1/memberships/{owner_a.id}",
        {"role_id": str(Role.objects.create(tenant=tenant_a, name="Sales").id)},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert demote.status_code == 400
    assert "role_id" in demote.json()["field_errors"]

    revoke = auth_client.delete(
        f"/api/v1/memberships/{owner_a.id}", HTTP_X_CSRFTOKEN=csrf
    )
    assert revoke.status_code == 400
    assert "membership" in revoke.json()["field_errors"]

    # Owner kedua ditambahkan → keduanya boleh dicabut/diturunkan
    other = User.objects.create_user(email="co-owner@example.com", password="rahasia123")
    other.status = UserStatus.ACTIVE
    other.email_verified_at = timezone.now()
    other.save()
    TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant_a, user=other, role=owner_a.role, status=MembershipStatus.ACTIVE
    )
    ok = auth_client.delete(f"/api/v1/memberships/{owner_a.id}", HTTP_X_CSRFTOKEN=csrf)
    assert ok.status_code == 200
    owner_a.refresh_from_db()
    assert owner_a.status == MembershipStatus.REVOKED
    assert "memberships.revoked" in _audit_actions()

    # akses langsung hilang: sesi requester tanpa membership ACTIVE → ditolak
    assert auth_client.get("/api/v1/memberships").status_code == 403

    # idempoten: revoke anggota lain dua kali (requester = co-owner yang masih aktif)
    client.force_login(other)
    csrf2 = _csrf(client)
    staff, _ = _make_staff(db, tenant_a, "staff@example.com", "Staff", ["bookings.read"])
    member = TenantMembership.objects.without_tenant_guard().get(tenant=tenant_a, user=staff)
    first = client.delete(f"/api/v1/memberships/{member.id}", HTTP_X_CSRFTOKEN=csrf2)
    assert first.status_code == 200
    assert first.json()["changed"] is True
    second = client.delete(f"/api/v1/memberships/{member.id}", HTTP_X_CSRFTOKEN=csrf2)
    assert second.status_code == 200
    assert second.json()["changed"] is False


@pytest.mark.django_db
def test_membership_detail_cross_tenant_404(client, db, user, owner_a, tenant_a, tenant_b):
    foreign_user = User.objects.create_user(email="b@example.com", password="rahasia123")
    foreign_role = Role.objects.create(tenant=tenant_b, name="Owner")
    foreign_member = TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant_b, user=foreign_user, role=foreign_role, status=MembershipStatus.ACTIVE
    )
    client.force_login(user)
    csrf = _csrf(client)
    patched = client.patch(
        f"/api/v1/memberships/{foreign_member.id}",
        {"role_id": str(foreign_role.id)},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert patched.status_code == 404
    deleted = client.delete(f"/api/v1/memberships/{foreign_member.id}", HTTP_X_CSRFTOKEN=csrf)
    assert deleted.status_code == 404
    foreign_member.refresh_from_db()
    assert foreign_member.status == MembershipStatus.ACTIVE


# ---------------------------------------------------------------------- roles --


@pytest.mark.django_db
def test_provisioning_creates_default_roles_settings_and_system_owner(db, user, tenant_a):
    tenant_a.created_by = user
    tenant_a.save(update_fields=["created_by"])
    tenant = provision_workspace(user, tenant_a.slug)
    names = set(Role.objects.filter(tenant=tenant).values_list("name", flat=True))
    assert {"Owner", "Admin", "Sales", "Finance", "Operations", "Document Reviewer"} <= names
    owner_role = Role.objects.get(tenant=tenant, name="Owner")
    assert owner_role.is_system is True
    assert owner_role.permissions_json == ["*"]
    assert TenantSettings.objects.filter(tenant=tenant).exists()
    # idempoten
    provision_workspace(user, tenant.slug)
    assert Role.objects.filter(tenant=tenant).count() == len(names)


@pytest.mark.django_db
def test_role_list_returns_tenant_roles_scoped(client, db, user, owner_a, tenant_a, tenant_b):
    Role.objects.create(tenant=tenant_a, name="CustomA", permissions_json=["bookings.read"])
    Role.objects.create(tenant=tenant_b, name="CustomB", permissions_json=["bookings.read"])
    client.force_login(user)
    response = client.get("/api/v1/roles")
    assert response.status_code == 200
    names = {r["name"] for r in response.json()["results"]}
    assert "CustomA" in names and "CustomB" not in names


@pytest.mark.django_db
@pytest.mark.parametrize(
    "name,permissions,status_code",
    [
        ("Owner", ["bookings.read"], 400),  # nama dilindungi sistem
        ("Spesial", ["*"], 400),  # wildcard global hanya Owner sistem
        ("Spesial", ["Bad Pattern!"], 400),  # tidak sesuai pola domain.object.action
        ("Spesial", ["bookings.*"], 201),  # wildcard antar-segmen diizinkan
    ],
)
def test_role_create_validation(auth_client, owner_a, name, permissions, status_code):
    csrf = _csrf(auth_client)
    response = auth_client.post(
        "/api/v1/roles",
        {"name": name, "permissions": permissions},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == status_code
    if status_code == 201:
        assert response.json()["role"]["permissions"] == permissions
        assert response.json()["role"]["is_system"] is False


@pytest.mark.django_db
def test_role_create_duplicate_name_rejected(auth_client, owner_a, tenant_a):
    Role.objects.create(tenant=tenant_a, name="Custom", permissions_json=[])
    csrf = _csrf(auth_client)
    response = auth_client.post(
        "/api/v1/roles",
        {"name": "Custom", "permissions": ["bookings.read"]},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 400
    assert "name" in response.json()["field_errors"]


@pytest.mark.django_db
def test_role_update_and_delete_flow(auth_client, owner_a, tenant_a):
    role = Role.objects.create(tenant=tenant_a, name="Custom", permissions_json=["bookings.read"])
    csrf = _csrf(auth_client)
    patched = auth_client.patch(
        f"/api/v1/roles/{role.id}",
        {"name": "Custom Renamed", "permissions": ["bookings.create", "bookings.read"]},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert patched.status_code == 200
    role.refresh_from_db()
    assert role.name == "Custom Renamed"
    assert "roles.updated" in _audit_actions()

    deleted = auth_client.delete(f"/api/v1/roles/{role.id}", HTTP_X_CSRFTOKEN=csrf)
    assert deleted.status_code == 204
    assert not Role.objects.filter(pk=role.pk).exists()
    assert "roles.deleted" in _audit_actions()


@pytest.mark.django_db
def test_system_role_immutable_and_undeletable(auth_client, owner_a, tenant_a):
    owner_role = owner_a.role
    owner_role.is_system = True
    owner_role.save(update_fields=["is_system"])
    csrf = _csrf(auth_client)
    patched = auth_client.patch(
        f"/api/v1/roles/{owner_role.id}",
        {"permissions": ["bookings.read"]},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert patched.status_code == 400
    deleted = auth_client.delete(f"/api/v1/roles/{owner_role.id}", HTTP_X_CSRFTOKEN=csrf)
    assert deleted.status_code == 400
    owner_role.refresh_from_db()
    assert owner_role.permissions_json == ["*"]


@pytest.mark.django_db
def test_role_in_use_cannot_be_deleted(auth_client, db, tenant_a, owner_a, verified_user):
    role = Role.objects.create(tenant=tenant_a, name="InUse", permissions_json=["bookings.read"])
    TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant_a, user=verified_user, role=role, status=MembershipStatus.ACTIVE
    )
    csrf = _csrf(auth_client)
    response = auth_client.delete(f"/api/v1/roles/{role.id}", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 400
    assert Role.objects.filter(pk=role.pk).exists()


@pytest.mark.django_db
def test_role_detail_cross_tenant_404(auth_client, tenant_b, owner_a):
    foreign = Role.objects.create(tenant=tenant_b, name="SalesB", permissions_json=[])
    csrf = _csrf(auth_client)
    response = auth_client.patch(
        f"/api/v1/roles/{foreign.id}",
        {"name": "Hacked"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_roles_denied_for_sales(client, db, user, owner_a, tenant_a):
    sales_user = User.objects.create_user(email="sales3@example.com", password="rahasia123")
    sales_user.status = UserStatus.ACTIVE
    sales_user.email_verified_at = timezone.now()
    sales_user.save()
    TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant_a,
        user=sales_user,
        role=Role.objects.create(tenant=tenant_a, name="SalesOnly", permissions_json=["bookings.read"]),
        status=MembershipStatus.ACTIVE,
    )
    client.force_login(sales_user)
    assert client.get("/api/v1/roles").status_code == 403
    csrf = _csrf(client)
    denied = client.post(
        "/api/v1/roles",
        {"name": "X", "permissions": ["bookings.read"]},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert denied.status_code == 403


# ------------------------------------------------------------- bank accounts --


@pytest.mark.django_db
def test_bank_account_masks_number_and_never_stores_full(auth_client, owner_a, tenant_a):
    csrf = _csrf(auth_client)
    full = "1234567890123"
    response = auth_client.post(
        "/api/v1/bank-accounts",
        {"bank_name": "BCA", "account_name": "PT Travel A", "account_number": full},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 201
    payload = response.json()["bank_account"]
    assert payload["account_masked"] == "*********0123"  # 4 digit terakhir saja
    assert full not in str(response.content)

    stored = TravelBankAccount.objects.without_tenant_guard().get(pk=payload["id"])
    assert full not in stored.account_masked
    assert stored.account_masked == mask_account_number(full)

    # audit juga tidak pernah menyimpan nomor penuh
    event = AuditEvent.objects.get(action="bank_accounts.created")
    assert full not in str(event.changes_json)
    assert event.changes_json["account_masked"] == payload["account_masked"]


@pytest.mark.django_db
def test_bank_account_list_scoped_and_finance_role(client, db, user, owner_a, tenant_a, tenant_b):
    _seed_bank(tenant_a, bank_name="BCA")
    _seed_bank(tenant_b, bank_name="MANDIRI", account_masked="************9999")

    # finance role: punya akses rekening (matriks §3)
    finance_user = User.objects.create_user(email="finance@example.com", password="rahasia123")
    finance_user.status = UserStatus.ACTIVE
    finance_user.email_verified_at = timezone.now()
    finance_user.save()
    TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant_a,
        user=finance_user,
        role=Role.objects.create(
            tenant=tenant_a,
            name="Finance",
            permissions_json=["bank_accounts.read", "bank_accounts.write"],
        ),
        status=MembershipStatus.ACTIVE,
    )
    client.force_login(finance_user)
    listed = client.get("/api/v1/bank-accounts")
    assert listed.status_code == 200
    names = {r["bank_name"] for r in listed.json()["results"]}
    assert names == {"BCA"}  # rekening tenant_b tidak bocor

    csrf = _csrf(client)
    created = client.post(
        "/api/v1/bank-accounts",
        {"bank_name": "BNI", "account_name": "PT A", "account_number": "9876543210"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert created.status_code == 201


@pytest.mark.django_db
@pytest.mark.parametrize("role_name,perms", [("Admin", ["memberships.read"]), ("Sales", ["bookings.read"])])
def test_bank_accounts_denied_without_finance_grant(
    client, db, user, owner_a, tenant_a, role_name, perms
):
    member_user = User.objects.create_user(
        email=f"{role_name.lower()}@example.com", password="rahasia123"
    )
    member_user.status = UserStatus.ACTIVE
    member_user.email_verified_at = timezone.now()
    member_user.save()
    TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant_a,
        user=member_user,
        role=Role.objects.create(tenant=tenant_a, name=role_name, permissions_json=perms),
        status=MembershipStatus.ACTIVE,
    )
    client.force_login(member_user)
    assert client.get("/api/v1/bank-accounts").status_code == 403
    csrf = _csrf(client)
    denied = client.post(
        "/api/v1/bank-accounts",
        {"bank_name": "X", "account_name": "Y", "account_number": "123456"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert denied.status_code == 403


@pytest.mark.django_db
def test_bank_account_patch_and_cross_tenant_404(auth_client, owner_a, tenant_a, tenant_b):
    own = _seed_bank(tenant_a, bank_name="BCA")
    foreign = _seed_bank(tenant_b, bank_name="BRI", account_masked="************1111")
    csrf = _csrf(auth_client)

    patched = auth_client.patch(
        f"/api/v1/bank-accounts/{own.id}",
        {"active": False},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert patched.status_code == 200
    assert patched.json()["bank_account"]["active"] is False
    assert "bank_accounts.updated" in _audit_actions()

    cross = auth_client.patch(
        f"/api/v1/bank-accounts/{foreign.id}",
        {"active": False},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert cross.status_code == 404
    foreign.refresh_from_db()
    assert foreign.active is True


@pytest.mark.django_db
def test_bank_account_duplicate_masked_rejected(auth_client, owner_a, tenant_a):
    _seed_bank(tenant_a, bank_name="BCA", account_masked="************1234")
    csrf = _csrf(auth_client)
    response = auth_client.post(
        "/api/v1/bank-accounts",
        {"bank_name": "BCA", "account_name": "PT Travel", "account_number": "0000000000001234"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 400
    assert "account_number" in response.json()["field_errors"]


# ---------------------------------------------------------------------- audit --


@pytest.mark.django_db
def test_audit_event_is_append_only(db, tenant_a):
    event = AuditEvent.objects.create(
        tenant=tenant_a, action="test.action", object_type="x", object_id="1"
    )
    with pytest.raises(Exception) as exc:
        event.action = "mutated"
        event.save()
    assert "append-only" in str(exc.value)
    with pytest.raises(Exception) as exc:
        event.delete()
    assert "append-only" in str(exc.value)


def test_audit_redact_masks_sensitive_keys():
    cleaned = redact(
        {
            "password": "rahasia",
            "account_number": "1234567890",
            "otp": "123456",
            "nested": {"api_token": "abc", "safe": 1},
            "items": [{"secret_key": "s"}],
        }
    )
    assert cleaned["password"] == "***"
    assert cleaned["account_number"] == "***"
    assert cleaned["otp"] == "***"
    assert cleaned["nested"]["api_token"] == "***"
    assert cleaned["nested"]["safe"] == 1
    assert cleaned["items"][0]["secret_key"] == "***"


@pytest.mark.django_db
def test_audit_failure_does_not_break_operation(db, monkeypatch):
    from django.db import DatabaseError

    from modules.audit import services as audit_services

    class _FailingManager:
        @staticmethod
        def create(**kwargs):
            raise DatabaseError("audit store down")

    class _FailingEvent:
        objects = _FailingManager()

    monkeypatch.setattr(audit_services, "AuditEvent", _FailingEvent)
    # log_event menangkap kegagalan → tidak melempar ke jalur utama
    assert audit_services.log_event(action="x.y") is None


@pytest.mark.django_db
def test_workspace_switch_writes_audit(client, user, owner_a, tenant_a, tenant_b):
    _add_member(db=None, user=user, tenant=tenant_b, role_name="Sales", perms=["bookings.read"])
    client.force_login(user)
    csrf = _csrf(client)
    response = client.post(
        "/api/v1/workspaces/switch",
        {"slug": tenant_b.slug},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 200
    event = AuditEvent.objects.filter(action="workspaces.switched", tenant=tenant_b).first()
    assert event is not None
    assert event.actor_id == user.id
    assert event.changes_json == {"slug": tenant_b.slug}


@pytest.mark.django_db
def test_trial_convert_writes_audit(client, db, user, owner_a, tenant_a):
    from modules.trial.services import convert_trial, start_trial

    start_trial(tenant_a)
    convert_trial(tenant_a, actor=user, trigger="manual")
    event = AuditEvent.objects.filter(action="trial.converted", tenant=tenant_a).first()
    assert event is not None
    assert event.changes_json["trigger"] == "manual"
    assert event.changes_json["to_state"] == "ACTIVE"


# ----------------------------------------------------------------------- RLS --


@pytest.mark.django_db
def test_bank_account_table_has_enforced_rls_policy(db):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
            "WHERE relname = 'travel_finance_travelbankaccount'"
        )
        row = cursor.fetchone()
        assert row == (True, True), "tabel rekening harus ENABLE+FORCE RLS (ADR-0003 §3)"

        cursor.execute(
            "SELECT qual, with_check FROM pg_policies "
            "WHERE tablename = 'travel_finance_travelbankaccount'"
        )
        policy = cursor.fetchone()
        assert policy is not None
        qual, with_check = policy
        for clause in (qual, with_check):
            assert "current_setting('app.tenant_id'" in clause
            assert "NULLIF" in clause  # konteks kosong → NULL → deny (fail-closed)
