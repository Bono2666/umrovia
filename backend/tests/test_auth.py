"""S02 — Auth flows: register → verifikasi → login/logout/me → reset (Spec §8.1, T07)."""
import re
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from modules.identity.models import AuthToken, User, UserStatus
from modules.tenants.models import Tenant, TenantMembership
from modules.trial.models import TenantTrial

REGISTER_PAYLOAD = {
    "email": "baru@travelkita.id",
    "password": "kata-sandi-kuat",
    "travel_name": "PT Travel Kita",
    "slug": "travel-kita",
    "agree_terms": True,
}


def _extract_token(message) -> str:
    match = re.search(r"token=([A-Za-z0-9_\-]+)", message.body)
    assert match, "link berisi token tidak ditemukan di email"
    return match.group(1)


# ---------------------------------------------------------------- register --


@pytest.mark.django_db
def test_register_creates_user_tenant_and_sends_email(client, settings):
    response = client.post("/api/v1/auth/register", REGISTER_PAYLOAD, content_type="application/json")
    assert response.status_code == 201
    assert response.json()["status"] == "verification_sent"

    user = User.objects.get(email="baru@travelkita.id")
    assert user.status == UserStatus.PENDING_VERIFICATION
    assert user.terms_accepted_at is not None
    tenant = Tenant.objects.get(slug="travel-kita")
    assert tenant.state == "PENDING_EMAIL"
    assert tenant.created_by == user
    assert len(mail.outbox) == 1
    assert "token=" in mail.outbox[0].body


@pytest.mark.django_db
def test_register_duplicate_email_is_generic(client):
    """Anti-enumeration: respons sama, tidak ada tenant/workspace baru."""
    client.post("/api/v1/auth/register", REGISTER_PAYLOAD, content_type="application/json")
    tenants_before = Tenant.objects.count()
    response = client.post("/api/v1/auth/register", REGISTER_PAYLOAD, content_type="application/json")
    assert response.status_code == 200
    assert response.json()["status"] == "verification_sent"
    assert Tenant.objects.count() == tenants_before


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field,value",
    [
        ("slug", "admin"),  # reserved
        ("slug", "travel-a"),  # terpakai (butuh tenant fixture)
        ("slug", "Slug_Salah"),  # format invalid
        ("agree_terms", False),
        ("password", "pendek"),
        ("email", "bukan-email"),
    ],
)
def test_register_validation_rejects_bad_input(client, db, field, value):
    Tenant.objects.create(slug="travel-a", legal_name="PT A", display_name="A")
    payload = {**REGISTER_PAYLOAD, field: value}
    response = client.post("/api/v1/auth/register", payload, content_type="application/json")
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "bad_request" and body["field_errors"]


# ------------------------------------------------------------- verifikasi ---


@pytest.mark.django_db
def test_verify_email_provisions_workspace_and_activates(client, mailoutbox):
    client.post("/api/v1/auth/register", REGISTER_PAYLOAD, content_type="application/json")
    token = _extract_token(mailoutbox[0])

    response = client.post(
        "/api/v1/auth/verify-email", {"token": token}, content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "verified"

    user = User.objects.get(email="baru@travelkita.id")
    assert user.status == UserStatus.ACTIVE and user.is_email_verified
    tenant = Tenant.objects.get(slug="travel-kita")
    # S04: provisioning penuh → state TRIAL + trial record aktif (§7.1 langkah 3)
    assert tenant.state == "TRIAL"
    trial = TenantTrial.objects.get(tenant=tenant)
    assert trial.status == "RUNNING" and trial.converted_at is None
    membership = TenantMembership.objects.without_tenant_guard().get(tenant=tenant, user=user)
    assert membership.status == "ACTIVE" and membership.role.name == "Owner"

    # setelah verifikasi, login berfungsi
    login = client.post(
        "/api/v1/auth/login",
        {"email": "baru@travelkita.id", "password": "kata-sandi-kuat"},
        content_type="application/json",
    )
    assert login.status_code == 200
    assert login.json()["memberships"][0]["tenant"]["slug"] == "travel-kita"


@pytest.mark.django_db
def test_verify_email_provisioning_is_idempotent(client, mailoutbox):
    client.post("/api/v1/auth/register", REGISTER_PAYLOAD, content_type="application/json")
    token = _extract_token(mailoutbox[0])
    client.post("/api/v1/auth/verify-email", {"token": token}, content_type="application/json")
    # token sudah terpakai → gagal, tetapi workspace tetap satu (tidak dobel)
    again = client.post(
        "/api/v1/auth/verify-email", {"token": token}, content_type="application/json"
    )
    assert again.status_code == 400
    assert again.json()["code"] == "token_used"
    assert Tenant.objects.filter(slug="travel-kita").count() == 1
    assert TenantMembership.objects.without_tenant_guard().count() == 1


@pytest.mark.django_db
def test_verify_invalid_token_rejected(client):
    response = client.post(
        "/api/v1/auth/verify-email", {"token": "ngasal-banget"}, content_type="application/json"
    )
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_token"


@pytest.mark.django_db
def test_verify_expired_token_rejected(client, mailoutbox):
    client.post("/api/v1/auth/register", REGISTER_PAYLOAD, content_type="application/json")
    token = _extract_token(mailoutbox[0])
    AuthToken.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
    response = client.post(
        "/api/v1/auth/verify-email", {"token": token}, content_type="application/json"
    )
    assert response.status_code == 400
    assert response.json()["code"] == "token_expired"


@pytest.mark.django_db
def test_resend_verification_invalidates_old_token(client, mailoutbox):
    client.post("/api/v1/auth/register", REGISTER_PAYLOAD, content_type="application/json")
    old_token = _extract_token(mailoutbox[0])
    response = client.post(
        "/api/v1/auth/resend-verification",
        {"email": REGISTER_PAYLOAD["email"]},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert len(mail.outbox) == 2
    # token lama tidak berlaku, token baru bisa dipakai
    old = client.post(
        "/api/v1/auth/verify-email", {"token": old_token}, content_type="application/json"
    )
    assert old.json()["code"] in ("token_used", "invalid_token")
    new_token = _extract_token(mail.outbox[1])
    new = client.post(
        "/api/v1/auth/verify-email", {"token": new_token}, content_type="application/json"
    )
    assert new.status_code == 200


# ----------------------------------------------------------------- login ----


@pytest.mark.django_db
def test_login_requires_verified_email(client, mailoutbox):
    client.post("/api/v1/auth/register", REGISTER_PAYLOAD, content_type="application/json")
    response = client.post(
        "/api/v1/auth/login",
        {"email": REGISTER_PAYLOAD["email"], "password": REGISTER_PAYLOAD["password"]},
        content_type="application/json",
    )
    assert response.status_code == 403
    assert response.json()["code"] == "email_not_verified"


@pytest.mark.django_db
def test_login_wrong_password(client, verified_user):
    response = client.post(
        "/api/v1/auth/login",
        {"email": "verified@example.com", "password": "salah-juga"},
        content_type="application/json",
    )
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


@pytest.mark.django_db
def test_login_me_logout_flow(client, owner_a, user):
    login = client.post(
        "/api/v1/auth/login",
        {"email": "owner@example.com", "password": "rahasia123"},
        content_type="application/json",
    )
    assert login.status_code == 200
    me = client.get("/api/v1/me")
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "owner@example.com"
    assert body["memberships"][0]["tenant"]["slug"] == "travel-a"
    assert body["memberships"][0]["role"] == "Owner"

    # logout perlu CSRF (SessionAuthentication)
    csrf = client.get("/api/v1/auth/csrf")
    assert csrf.status_code == 200
    token = csrf.json()["csrfToken"]
    out = client.post(
        "/api/v1/auth/logout", HTTP_X_CSRFTOKEN=token, content_type="application/json"
    )
    assert out.status_code == 200
    # SessionAuthentication tanpa WWW-Authenticate → DRF menurunkan 401 jadi 403
    after = client.get("/api/v1/me")
    assert after.status_code == 403
    assert after.json()["code"] == "not_authenticated"


# -------------------------------------------------------- password reset ----


@pytest.mark.django_db
def test_forgot_and_reset_password_flow(client, verified_user, mailoutbox):
    forgot = client.post(
        "/api/v1/auth/password/forgot",
        {"email": "verified@example.com"},
        content_type="application/json",
    )
    assert forgot.status_code == 200
    assert forgot.json()["status"] == "if_registered"  # respons generik anti-enumeration
    assert len(mail.outbox) == 1
    token = _extract_token(mailoutbox[0])

    reset = client.post(
        "/api/v1/auth/password/reset",
        {"token": token, "password": "sandis-baru-kuat"},
        content_type="application/json",
    )
    assert reset.status_code == 200

    # token sekali pakai
    reuse = client.post(
        "/api/v1/auth/password/reset",
        {"token": token, "password": "lagi-lagi-kuat"},
        content_type="application/json",
    )
    assert reuse.status_code == 400 and reuse.json()["code"] == "token_used"

    # login dengan password baru
    login = client.post(
        "/api/v1/auth/login",
        {"email": "verified@example.com", "password": "sandis-baru-kuat"},
        content_type="application/json",
    )
    assert login.status_code == 200


@pytest.mark.django_db
def test_forgot_unknown_email_still_generic(client, db):
    response = client.post(
        "/api/v1/auth/password/forgot", {"email": "tidakada@contoh.id"}, content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "if_registered"
    assert len(mail.outbox) == 0


# --------------------------------------------------------------- throttle ---


@pytest.mark.django_db
def test_login_throttled_after_rate_exceeded(client, owner_a):
    """Rate limit login aktif: setelah rate terlampaui → 429 (Spec §8: rate limit auth)."""
    from django.core.cache import cache
    from rest_framework.throttling import SimpleRateThrottle

    original = SimpleRateThrottle.THROTTLE_RATES
    SimpleRateThrottle.THROTTLE_RATES = {**original, "auth-login": "3/min"}
    cache.clear()
    try:
        payload = {"email": "owner@example.com", "password": "salah-terus"}
        codes = [
            client.post("/api/v1/auth/login", payload, content_type="application/json").status_code
            for _ in range(5)
        ]
    finally:
        SimpleRateThrottle.THROTTLE_RATES = original
    assert 429 in codes, f"throttle tidak aktif: {codes}"
    assert codes[-1] == 429
