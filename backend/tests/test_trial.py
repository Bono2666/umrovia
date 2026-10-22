"""S04 — Trial lifecycle: start, kuota, konversi, expiry (Spec §5.1, §6.1, §7.1–7.2).

Membuktikan test case MVP: TR01 (30×24 jam persis), TR02 (kuota 20/21 ditolak),
TR03 (delete tak mengembalikan kuota), TR04 (limit 3 internal user), TR08
(expiry → ACTIVE otomatis tanpa bill), TR09 (konversi dini tunggal, idempoten).
Exit gate Roadmap S04: "Trial → active without auto-charge".
"""
from datetime import timedelta

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from modules.tenants.models import (
    Environment,
    EnvironmentState,
    MembershipStatus,
    Role,
    TenantEnvironment,
    TenantMembership,
    TenantState,
)
from modules.tenants.services import provision_workspace
from modules.trial import services as trial_services
from modules.trial.exceptions import TrialUserLimit
from modules.trial.models import DemoBooking, TenantTrial, TenantTrialEvent, TrialEventType, TrialStatus

# ------------------------------------------------------------------ fixtures --


@pytest.fixture
def trial_a(db, user, tenant_a):
    """Tenant travel-a terprovisioning penuh: Owner aktif + trial RUNNING."""
    tenant_a.created_by = user
    tenant_a.state = TenantState.PENDING_EMAIL
    tenant_a.save()
    tenant = provision_workspace(user, "travel-a")
    return tenant, TenantTrial.objects.get(tenant=tenant)


def _add_member(tenant, email: str, role_name: str, perms: list) -> TenantMembership:
    from modules.identity.models import User

    member_user = User.objects.create_user(email=email, password="x-pass-123")
    role, _ = Role.objects.get_or_create(tenant=tenant, name=role_name, defaults={"permissions_json": perms})
    return TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant, user=member_user, role=role, status=MembershipStatus.ACTIVE
    )


def _csrf(client) -> str:
    return client.get("/api/v1/auth/csrf").json()["csrfToken"]


# ------------------------------------------------------- TR01: start + state --


@pytest.mark.django_db
def test_tr01_provision_starts_trial_30_days(db, user, tenant_a):
    """TR01: trial mulai saat provisioning committed; 30×24 jam persis; state TRIAL."""
    before = timezone.now()
    tenant_a.created_by = user
    tenant_a.state = TenantState.PENDING_EMAIL
    tenant_a.save()
    tenant = provision_workspace(user, "travel-a")

    assert tenant.state == TenantState.TRIAL
    trial = TenantTrial.objects.get(tenant=tenant)
    assert trial.status == TrialStatus.RUNNING
    assert trial.converted_at is None
    assert before <= trial.started_at <= trial.ends_at
    assert trial.ends_at - trial.started_at == timedelta(days=settings.TRIAL_DAYS)
    # snapshot entitlement immutable (§5.1) — 20 booking demo / 3 user (POL-08)
    assert trial.dummy_booking_limit == 20
    assert trial.internal_users_limit == 3
    # environment demo aktif; produksi belum ada (trial, §7.2)
    assert TenantEnvironment.objects.filter(
        tenant=tenant, environment=Environment.DEMO, state=EnvironmentState.ACTIVE
    ).exists()
    assert not TenantEnvironment.objects.filter(tenant=tenant, environment=Environment.PRODUCTION).exists()
    # event log STARTED (append-only, §5.1)
    assert TenantTrialEvent.objects.filter(tenant=tenant, type=TrialEventType.STARTED).count() == 1


@pytest.mark.django_db
def test_provisioning_retry_idempotent(trial_a):
    tenant, trial = trial_a
    again = provision_workspace(tenant.created_by, "travel-a")
    assert TenantTrial.objects.filter(tenant=again).count() == 1
    assert TenantMembership.objects.without_tenant_guard().filter(tenant=again).count() == 1


# ------------------------------------------------------- status (§8.2/§8.7) --


@pytest.mark.django_db
def test_trial_status_payload_spec_example(client, trial_a):
    tenant, trial = trial_a
    client.force_login(tenant.created_by)
    response = client.get("/api/v1/trial/status")
    assert response.status_code == 200
    body = response.json()
    assert body["trial_status"] == "RUNNING"
    assert body["dummy_bookings_used"] == 0
    assert body["dummy_bookings_limit"] == 20
    assert body["internal_users_used"] == 1  # Owner
    assert body["internal_users_limit"] == 3
    assert body["trial_price_idr"] == 0
    assert body["can_convert_now"] is True
    assert body["started_at"] and body["ends_at"]


# ------------------------------------------------------------- TR02/TR03 kuota --


@pytest.mark.django_db
def test_tr02_demo_booking_quota_20_then_rejected(client, trial_a):
    tenant, trial = trial_a
    client.force_login(tenant.created_by)
    csrf = _csrf(client)
    for index in range(20):
        response = client.post(
            "/api/v1/trial/demo-bookings",
            {"label": f"Booking demo {index + 1}"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 201, response.content
        assert response.json()["booking"]["code"].startswith("DEMO-")

    rejected = client.post(
        "/api/v1/trial/demo-bookings",
        {"label": "Booking ke-21"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert rejected.status_code == 403
    assert rejected.json()["code"] == "TRIAL_QUOTA_EXCEEDED"
    trial.refresh_from_db()
    assert trial.dummy_count == 20
    assert DemoBooking.objects.filter(tenant=tenant).count() == 20


@pytest.mark.django_db
def test_tr03_delete_demo_record_keeps_counter(trial_a):
    tenant, trial = trial_a
    booking = trial_services.create_demo_booking(tenant, label="Demo dihapus")
    trial.refresh_from_db()
    assert trial.dummy_count == 1
    booking.delete()  # §7.1 langkah 5: delete TIDAK mengembalikan kuota
    trial.refresh_from_db()
    assert trial.dummy_count == 1
    assert not DemoBooking.objects.filter(pk=booking.pk).exists()


@pytest.mark.django_db
def test_counter_rolled_back_when_create_fails(trial_a, monkeypatch):
    """§7.1 langkah 5: increment SEBELUM create; create gagal → rollback counter."""
    tenant, trial = trial_a

    class _StubManager:
        @staticmethod
        def create(**kwargs):
            raise RuntimeError("simulasi kegagalan DB saat create booking")

    class _FailingCreate:
        objects = _StubManager()

    monkeypatch.setattr(trial_services, "DemoBooking", _FailingCreate)
    with pytest.raises(RuntimeError):
        trial_services.create_demo_booking(tenant, label="tak pernah tersimpan")
    trial.refresh_from_db()
    assert trial.dummy_count == 0


# ------------------------------------------------------------------ TR04 user --


@pytest.mark.django_db
def test_tr04_internal_user_limit(trial_a):
    """TR04: maksimal 3 internal user aktif; user keempat ditolak."""
    tenant, trial = trial_a
    assert trial.internal_users_limit == 3
    trial_services.assert_internal_user_quota(tenant)  # 1 owner → lolos

    _add_member(tenant, "cs1@travela.id", "Sales", ["bookings.read"])
    _add_member(tenant, "cs2@travela.id", "Finance", ["payments.verify"])  # → 3 aktif (batas)
    # TR04: penambahan user KEEMPAT ditolak guard kuota
    with pytest.raises(TrialUserLimit) as exc:
        trial_services.assert_internal_user_quota(tenant)
    assert exc.value.default_code == "TRIAL_USER_LIMIT"

    # tenant non-trial (sudah konversi) lolos tanpa cek
    trial.converted_at = timezone.now()
    trial.save(update_fields=["converted_at", "updated_at"])
    trial_services.assert_internal_user_quota(tenant)


# --------------------------------------------------------------- konversi --


@pytest.mark.django_db
def test_convert_requires_explicit_confirmation(client, trial_a):
    tenant, _ = trial_a
    client.force_login(tenant.created_by)
    csrf = _csrf(client)
    for payload in ({}, {"confirm": False}):
        response = client.post(
            "/api/v1/trial/convert", payload, content_type="application/json", HTTP_X_CSRFTOKEN=csrf
        )
        assert response.status_code == 400
        assert "confirm" in response.json()["field_errors"]


@pytest.mark.django_db
def test_tr09_early_conversion_single_and_idempotent(client, trial_a):
    """TR09: konversi dini tunggal → ACTIVE tanpa charge; ulang = idempoten."""
    tenant, trial = trial_a
    client.force_login(tenant.created_by)
    csrf = _csrf(client)

    first = client.post(
        "/api/v1/trial/convert",
        {"confirm": True},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert first.status_code == 200
    body = first.json()
    assert body["converted"] is True and body["converted_now"] is True
    assert body["trial_status"] == "CONVERTED_EARLY"
    assert body["tenant_state"] == "ACTIVE"
    assert body["trial_price_idr"] == 0  # POL-10: nol biaya saat konversi
    assert "wallet" in body["message"].lower()

    tenant.refresh_from_db()
    assert tenant.state == TenantState.ACTIVE
    assert tenant.active_at is not None
    trial.refresh_from_db()
    assert trial.converted_at is not None
    assert trial.converted_by_id == tenant.created_by_id
    # demo → read-only; namespace produksi aktif (§7.2 langkah 2)
    assert TenantEnvironment.objects.get(tenant=tenant, environment=Environment.DEMO).state == (
        EnvironmentState.READ_ONLY
    )
    assert TenantEnvironment.objects.get(tenant=tenant, environment=Environment.PRODUCTION).state == (
        EnvironmentState.ACTIVE
    )
    assert TenantTrialEvent.objects.filter(tenant=tenant, type=TrialEventType.CONVERTED_EARLY).count() == 1

    # idempoten — konversi ulang tidak mengubah apa pun (tidak ada reentry)
    converted_at_before = trial.converted_at
    second = client.post(
        "/api/v1/trial/convert",
        {"confirm": True},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert second.status_code == 200
    assert second.json()["converted_now"] is False
    trial.refresh_from_db()
    assert trial.converted_at == converted_at_before
    assert TenantTrialEvent.objects.filter(tenant=tenant, type=TrialEventType.CONVERTED_EARLY).count() == 1

    # demo writes ditutup setelah konversi (TR09/TR02 pasca-konversi)
    blocked = client.post(
        "/api/v1/trial/demo-bookings",
        {"label": "setelah konversi"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "TRIAL_ALREADY_USED"

    # data demo tetap terbaca read-only (§7.2 langkah 3)
    demo_data = client.get("/api/v1/trial/demo-data")
    assert demo_data.status_code == 200
    assert demo_data.json()["read_only"] is True


@pytest.mark.django_db
def test_convert_blocked_for_role_without_grant(client, db, trial_a):
    """Konversi = Owner saja (§3: Admin tidak punya `trial.convert`)."""
    tenant, _ = trial_a
    from modules.identity.models import User

    _add_member(tenant, "admin@travela.id", "Admin", ["trial.read", "trial.demo_booking.create"])
    admin_user = User.objects.get(email="admin@travela.id")
    client.force_login(admin_user)
    assert client.get("/api/v1/trial/status").status_code == 200  # Admin boleh lihat status
    response = client.post(
        "/api/v1/trial/convert",
        {"confirm": True},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=_csrf(client),
    )
    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


@pytest.mark.django_db
def test_demo_booking_allowed_for_sales_but_status_denied(client, db, trial_a):
    """demo-bookings: Admin/Sales (§8.2); status: Owner/Admin saja."""
    tenant, _ = trial_a
    from modules.identity.models import User

    _add_member(tenant, "sales@travela.id", "Sales", ["trial.demo_booking.create"])
    client.force_login(User.objects.get(email="sales@travela.id"))
    created = client.post(
        "/api/v1/trial/demo-bookings",
        {"label": "Dari Sales"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=_csrf(client),
    )
    assert created.status_code == 201
    assert client.get("/api/v1/trial/status").status_code == 403  # Sales tanpa trial.read
    assert client.post(
        "/api/v1/trial/convert", {"confirm": True}, content_type="application/json", HTTP_X_CSRFTOKEN=_csrf(client)
    ).status_code == 403


@pytest.mark.django_db
def test_demo_data_read_only_for_owner(client, db, trial_a):
    """demo-data: Role Owner (§8.2) — Admin tidak."""
    tenant, _ = trial_a
    from modules.identity.models import User

    _add_member(tenant, "admin2@travela.id", "Admin", ["trial.read", "trial.demo_booking.create"])
    client.force_login(User.objects.get(email="admin2@travela.id"))
    assert client.get("/api/v1/trial/demo-data").status_code == 403
    client.force_login(tenant.created_by)
    assert client.get("/api/v1/trial/demo-data").status_code == 200


# ------------------------------------------------------- TR08: expiry job --


@pytest.mark.django_db
def test_tr08_expiry_auto_active_without_bill(trial_a):
    """TR08: trial habis → ACTIVE otomatis, tanpa bill, tanpa suspensi."""
    tenant, trial = trial_a
    trial.ends_at = timezone.now() - timedelta(hours=1)
    trial.save(update_fields=["ends_at", "updated_at"])

    assert trial_services.expire_due_trials() == 1
    tenant.refresh_from_db()
    assert tenant.state == TenantState.ACTIVE  # bukan RESTRICTED/SUSPENDED (tanpa bill)
    trial.refresh_from_db()
    assert trial.status == TrialStatus.EXPIRED_CONVERTED
    assert trial.converted_at is not None
    assert trial.converted_by_id is None  # job, bukan actor
    assert TenantTrialEvent.objects.filter(tenant=tenant, type=TrialEventType.EXPIRED_CONVERTED).count() == 1

    # idempoten: jalankan ulang tidak mengkonversi dua kali
    assert trial_services.expire_due_trials() == 0
    assert TenantTrialEvent.objects.filter(tenant=tenant, type=TrialEventType.EXPIRED_CONVERTED).count() == 1


@pytest.mark.django_db
def test_expiry_skips_trial_not_yet_due(trial_a):
    tenant, trial = trial_a
    assert trial.ends_at > timezone.now()
    assert trial_services.expire_due_trials() == 0
    assert tenant.state == TenantState.TRIAL


@pytest.mark.django_db
def test_expiry_rechecks_under_lock_after_manual_convert(trial_a):
    """Race §6.1: konversi dini commit di antara scan ↔ lock → expiry melewatkan."""
    tenant, trial = trial_a
    trial.ends_at = timezone.now() - timedelta(hours=1)
    trial.save(update_fields=["ends_at", "updated_at"])
    # kandidat due teridentifikasi…
    due_ids = trial_services._due_trial_ids(timezone.now())
    assert trial.id in due_ids
    # …namun Owner mengkonversi lebih dulu (commit)…
    trial_services.convert_trial(tenant, actor=tenant.created_by, trigger="manual")
    # …expiry yang datang terlambat → re-check di bawah lock menolak (tanpa konversi ganda)
    assert trial_services.expire_trial(trial.id) is False
    trial.refresh_from_db()
    assert trial.status == TrialStatus.CONVERTED_EARLY
    assert TenantTrialEvent.objects.filter(tenant=tenant, type=TrialEventType.EXPIRED_CONVERTED).count() == 0


# ------------------------------------------------------------- append-only --


@pytest.mark.django_db
def test_trial_events_append_only(trial_a):
    tenant, _ = trial_a
    event = TenantTrialEvent.objects.filter(tenant=tenant, type=TrialEventType.STARTED).get()
    event.reason = "diubah"
    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ValidationError):
        event.delete()
