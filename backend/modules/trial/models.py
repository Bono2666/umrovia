"""Model trial (Spec §5.1: tenant_trials, tenant_trial_events, trial_entitlements).

Semua tabel di sini KONTROL-PLAN tenant (§5.1, bukan data bisnis §5.2) — tidak
di-RLS-kan (ADR-0003/ADR-0004): lifecycle trial berjalan saat provisioning
(sebelum context request) dan di job expiry tanpa context. Proteksi: kolom
tenant diisi server-side + otorisasi endpoint.

State trial (§6.1): `running | converted_early | expired_converted | extended`.
Konversi/expiry TIDAK PERNAH membuat charge berbayar (POL-10).
"""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from common.models import BaseAppModel, UUIDPkMixin
from modules.tenants.models import Tenant


class TrialStatus(models.TextChoices):
    RUNNING = "RUNNING", "Berjalan"
    CONVERTED_EARLY = "CONVERTED_EARLY", "Konversi dini → aktif"
    EXPIRED_CONVERTED = "EXPIRED_CONVERTED", "Berakhir → aktif"
    EXTENDED = "EXTENDED", "Diperpanjang platform (masih berjalan)"


class TrialEventType(models.TextChoices):
    STARTED = "STARTED", "Trial dimulai"
    REMINDER_D7 = "REMINDER_D7", "Reminder H-7"
    REMINDER_D3 = "REMINDER_D3", "Reminder H-3"
    REMINDER_D1 = "REMINDER_D1", "Reminder H-1"
    CONVERTED_EARLY = "CONVERTED_EARLY", "Konversi dini"
    EXPIRED_CONVERTED = "EXPIRED_CONVERTED", "Kedaluwarsa → aktif"
    EXTENDED = "EXTENDED", "Perpanjangan platform"


class TenantTrial(models.Model):
    """Trial satu tenant (UNIQUE tenant_id, §5.1). Kuota dummy booking atomik
    tersimpan di `dummy_count` (POL-08): delete record TIDAK mengembalikan kuota.

    `config_snapshot_json` = salinan entitlement saat trial mulai — immutable
    (§5.1); kuota dibaca dari snapshot agar tidak berubah di tengah jalan.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(Tenant, on_delete=models.PROTECT, related_name="trial")
    started_at = models.DateTimeField()
    ends_at = models.DateTimeField(db_index=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=32, choices=TrialStatus.choices, default=TrialStatus.RUNNING)
    dummy_count = models.PositiveIntegerField(default=0)
    converted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    config_snapshot_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Trial tenant"

    def __str__(self) -> str:
        return f"Trial {self.tenant.slug} ({self.status})"

    @property
    def is_running(self) -> bool:
        return self.converted_at is None and self.status in (TrialStatus.RUNNING, TrialStatus.EXTENDED)

    @property
    def dummy_booking_limit(self) -> int:
        return int(self.config_snapshot_json.get("dummy_booking_limit", 20))

    @property
    def internal_users_limit(self) -> int:
        return int(self.config_snapshot_json.get("internal_users_limit", 3))


class TrialEntitlement(models.Model):
    """Kuota trial per tenant (tenant_id PK, §5.1). Snapshot immutable kecuali
    admin override platform (S16); perubahan TIDAK mengubah trial yang sedang
    berjalan (trial membaca `config_snapshot_json`)."""

    tenant = models.OneToOneField(
        Tenant, on_delete=models.PROTECT, related_name="trial_entitlement", primary_key=True
    )
    internal_users_limit = models.PositiveIntegerField(default=3)
    dummy_booking_limit = models.PositiveIntegerField(default=20)
    trial_features_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Entitlement {self.tenant.slug}"


class TenantTrialEvent(UUIDPkMixin, models.Model):
    """Log event trial APPEND-ONLY (§5.1) — dilarang update/hapus."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="trial_events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    type = models.CharField(max_length=32, choices=TrialEventType.choices)
    reason = models.TextField(blank=True)
    metadata_json = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Event trial"
        ordering = ("-occurred_at",)
        indexes = [models.Index(fields=("tenant", "occurred_at"), name="tte_tenant_occurred_idx")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("tenant_trial_events bersifat append-only (Spec §5.1).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("tenant_trial_events bersifat append-only (Spec §5.1).")

    def __str__(self) -> str:
        return f"{self.type} @ {self.tenant.slug}"


class DemoBooking(BaseAppModel):
    """Placeholder data demo trial (POL-08/09, §7.1 langkah 4) dengan prefix
    `DEMO-` (demo ≠ produksi). Booking demo nyata berbasis environment menyusul
    di S09 dan menggantikan record ini — semantik counter (kuota tidak pernah
    dikurangi, TR03) dipertahankan di `TenantTrial.dummy_count`."""

    tenant = models.ForeignKey(Tenant, on_delete=models.PROTECT, related_name="demo_bookings")
    trial = models.ForeignKey(TenantTrial, on_delete=models.PROTECT, related_name="demo_bookings")
    code = models.CharField(max_length=32, unique=True, blank=True)
    label = models.CharField(max_length=200, blank=True)

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = f"DEMO-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.code
