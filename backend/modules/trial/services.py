"""Lifecycle trial (Spec §6.1, §7.1–7.2; POL-07..POL-10).

Aturan kunci:
- **Mulai** saat provisioning committed (TR01): `started_at` = waktu provisioning,
  `ends_at` = +TRIAL_DAYS×24 jam — timer server-side UTC (POL-07).
- **Kuota atomik** (§7.1 langkah 5): `dummy_count` di-`SELECT FOR UPDATE` +
  increment SEBELU create booking demo; bila create gagal, transaksi rollback
  (counter ikut kembali); delete record TIDAK mengembalikan kuota (TR02/TR03).
- **Konversi dini & expiry** memakai lock baris trial + tenant (§7.2 langkah 1,
  §6.1 `SELECT FOR UPDATE` untuk hindari race). Keduanya menghasilkan status
  `ACTIVE` TANPA charge berbayar (POL-10/TR08) — hanya transisi state + event log.
- Idempoten (TR09): konversi kedua tidak mengubah apa pun, tidak ada reentry.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from modules.audit.services import log_event
from modules.tenants.models import (
    Environment,
    EnvironmentState,
    MembershipStatus,
    Tenant,
    TenantEnvironment,
    TenantMembership,
    TenantState,
)
from modules.trial.exceptions import TrialAlreadyUsed, TrialQuotaExceeded, TrialUserLimit
from modules.trial.models import (
    DemoBooking,
    TenantTrial,
    TenantTrialEvent,
    TrialEntitlement,
    TrialEventType,
    TrialStatus,
)

logger = logging.getLogger(__name__)

CONVERT_TRIGGERS = ("manual", "expiry")


def log_trial_event(tenant, *, type_: str, actor=None, reason: str = "", metadata: dict | None = None) -> TenantTrialEvent:
    return TenantTrialEvent.objects.create(
        tenant=tenant, actor=actor, type=type_, reason=reason, metadata_json=metadata or {}
    )


def get_trial(tenant) -> TenantTrial:
    """Trial tenant; bila belum ada (data lama pra-S04) dibuat lazily (defensif)."""
    trial = TenantTrial.objects.filter(tenant=tenant).first()
    if trial is None:
        logger.warning("trial tidak ditemukan untuk tenant aktif — dibuat lazily", extra={"tenant": tenant.slug})
        trial = start_trial(tenant)
    return trial


@transaction.atomic
def start_trial(tenant: Tenant, *, started_at=None) -> TenantTrial:
    """Mulai trial (idempoten; §7.1 langkah 3) dan transisikan tenant → TRIAL."""
    existing = TenantTrial.objects.filter(tenant=tenant).first()
    if existing is not None:
        return existing

    entitlement, _ = TrialEntitlement.objects.get_or_create(
        tenant=tenant,
        defaults={
            "dummy_booking_limit": settings.TRIAL_DUMMY_BOOKING_LIMIT,
            "internal_users_limit": settings.TRIAL_INTERNAL_USER_LIMIT,
        },
    )
    started_at = started_at or timezone.now()
    trial = TenantTrial.objects.create(
        tenant=tenant,
        started_at=started_at,
        ends_at=started_at + timedelta(days=settings.TRIAL_DAYS),
        status=TrialStatus.RUNNING,
        config_snapshot_json={
            "dummy_booking_limit": entitlement.dummy_booking_limit,
            "internal_users_limit": entitlement.internal_users_limit,
            "trial_features_json": entitlement.trial_features_json,
            "trial_days": settings.TRIAL_DAYS,
        },
    )
    if tenant.state in (TenantState.PENDING_EMAIL, TenantState.PROVISIONING):
        tenant.state = TenantState.TRIAL
        tenant.save(update_fields=["state", "updated_at"])
    log_trial_event(
        tenant,
        type_=TrialEventType.STARTED,
        metadata={"started_at": started_at.isoformat(), "ends_at": trial.ends_at.isoformat()},
    )
    return trial


def assert_internal_user_quota(tenant) -> None:
    """Tolak penambahan internal user melebihi kuota trial (TR04).

    Dihitung dari membership ACTIVE nyata (portal user di luar hitungan).
    Dipanggil alur penambahan staff (S05) dan provisioning (owner pertama).
    Tenant non-trial (sudah terkonversi) lewat tanpa cek.
    """
    trial = TenantTrial.objects.filter(tenant=tenant).first()
    if trial is None or not trial.is_running:
        return
    used = TenantMembership.objects.without_tenant_guard().filter(
        tenant=tenant, status=MembershipStatus.ACTIVE
    ).count()
    if used >= trial.internal_users_limit:
        raise TrialUserLimit(
            f"Trial membatasi {trial.internal_users_limit} internal user aktif. "
            "Konversi ke workspace aktif untuk menambah staf."
        )


@transaction.atomic
def create_demo_booking(tenant, *, actor=None, label: str = "") -> DemoBooking:
    """Buat booking demo dengan kuota atomik (§7.1 langkah 4–5, TR02/TR03)."""
    trial = TenantTrial.objects.select_for_update().get(tenant=tenant)
    if trial.converted_at is not None:
        raise TrialAlreadyUsed()
    if trial.dummy_count >= trial.dummy_booking_limit:
        raise TrialQuotaExceeded(f"Kuota {trial.dummy_booking_limit} booking demo trial terpakai semua.")
    # increment SEBELUM create — bila create gagal, atomic rollback mengembalikan
    # counter (§7.1 langkah 5); delete record tidak pernah mengurangi counter.
    trial.dummy_count += 1
    trial.save(update_fields=["dummy_count", "updated_at"])
    return DemoBooking.objects.create(tenant=tenant, trial=trial, label=label)


def _convert_locked(tenant, trial: TenantTrial, *, actor, trigger: str) -> bool:
    """Konversi trial yang SUDAH ter-lock. True bila konversi baru terjadi.

    Tanpa charge berbayar (POL-10): hanya state tenant → ACTIVE, namespace
    produksi dibuat, demo menjadi read-only, event log.
    """
    if trial.converted_at is not None:
        return False
    tenant_locked = Tenant.objects.select_for_update().get(pk=tenant.pk)
    now = timezone.now()
    trial.converted_at = now
    trial.status = TrialStatus.CONVERTED_EARLY if trigger == "manual" else TrialStatus.EXPIRED_CONVERTED
    trial.converted_by = actor
    trial.save(update_fields=["converted_at", "status", "converted_by", "updated_at"])

    # Tutup demo writes: demo → read-only; namespace produksi aktif (§7.2 langkah 2)
    TenantEnvironment.objects.filter(tenant=tenant_locked, environment=Environment.DEMO).update(
        state=EnvironmentState.READ_ONLY
    )
    TenantEnvironment.objects.get_or_create(
        tenant=tenant_locked, environment=Environment.PRODUCTION, defaults={"state": EnvironmentState.ACTIVE}
    )
    tenant_locked.state = TenantState.ACTIVE
    if tenant_locked.active_at is None:
        tenant_locked.active_at = now  # kolom tenants.active_at (§5.1): saat berubah ACTIVE
    tenant_locked.save(update_fields=["state", "active_at", "updated_at"])

    event_type = TrialEventType.CONVERTED_EARLY if trigger == "manual" else TrialEventType.EXPIRED_CONVERTED
    log_trial_event(
        tenant_locked,
        type_=event_type,
        actor=actor,
        reason="Konversi dini oleh Owner" if trigger == "manual" else "Trial habis (job expiry)",
        metadata={"trigger": trigger, "converted_at": now.isoformat()},
    )
    tenant.state = tenant_locked.state  # sinkronkan state pada objek tenant milik caller
    # Audit tunggal di choke-point (S05): menutup semua jalur (manual + expiry job)
    log_event(
        action="trial.converted",
        tenant=tenant_locked,
        actor=actor,
        object_type="tenant_trial",
        object_id=trial.id,
        changes={"trigger": trigger, "from_state": "TRIAL", "to_state": tenant_locked.state},
    )
    return True


def convert_trial(tenant, *, actor, trigger: str = "manual") -> tuple[TenantTrial, bool]:
    """Konversi trial → ACTIVE (idempoten, TR09). Mengembalikan (trial, konversi_baru)."""
    if trigger not in CONVERT_TRIGGERS:
        raise ValueError(f"Trigger konversi tak dikenal: {trigger}")
    with transaction.atomic():
        trial = TenantTrial.objects.select_for_update().get(tenant=tenant)
        converted_now = _convert_locked(tenant, trial, actor=actor, trigger=trigger)
        return trial, converted_now


def _due_trial_ids(now) -> list:
    return list(
        TenantTrial.objects.filter(
            converted_at__isnull=True,
            status__in=[TrialStatus.RUNNING, TrialStatus.EXTENDED],
            ends_at__lte=now,
        ).values_list("id", flat=True)
    )


def expire_trial(trial_id) -> bool:
    """Konversi satu trial jatuh tempo. Re-check di bawah lock baris trial —
    konversi dini yang commit di antara scan ↔ lock tidak dikonversi ulang
    (§6.1: `SELECT FOR UPDATE` menghindari race dengan early conversion)."""
    with transaction.atomic():
        trial = TenantTrial.objects.select_for_update().filter(id=trial_id).first()
        if (
            trial is None
            or trial.converted_at is not None
            or trial.status not in (TrialStatus.RUNNING, TrialStatus.EXTENDED)
            or trial.ends_at > timezone.now()
        ):
            return False
        return _convert_locked(tenant=trial.tenant, trial=trial, actor=None, trigger="expiry")


def expire_due_trials() -> int:
    """Job `trial_expiry` (cron; orkestrasi scheduler menyusul di S17). TR08:
    auto-ACTIVE, tanpa bill, tanpa suspensi. Idempoten bila dijalankan ulang."""
    processed = 0
    for trial_id in _due_trial_ids(timezone.now()):
        if expire_trial(trial_id):
            processed += 1
    return processed


def status_payload(tenant, trial: TenantTrial) -> dict:
    """Payload `/trial/status` mengikuti contoh Spec §8.7."""
    used_members = TenantMembership.objects.without_tenant_guard().filter(
        tenant=tenant, status=MembershipStatus.ACTIVE
    ).count()
    return {
        "trial_status": trial.status,
        "started_at": trial.started_at.isoformat(),
        "ends_at": trial.ends_at.isoformat(),
        "converted_at": trial.converted_at.isoformat() if trial.converted_at else None,
        "dummy_bookings_used": trial.dummy_count,
        "dummy_bookings_limit": trial.dummy_booking_limit,
        "internal_users_used": used_members,
        "internal_users_limit": trial.internal_users_limit,
        "trial_price_idr": 0,
        "can_convert_now": trial.converted_at is None,
    }
