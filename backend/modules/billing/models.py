"""SaaS charge per booking-jamaah (POL-02..POL-06). Produksi saja; demo tidak ditagih.

Satu `BookingParticipant` = satu unit charge `initial`. Tarif disalin dari
`SaaSPriceVersion` saat peserta eligible. Refund tidak pernah menghapus atau
membalik ledger: kredit kompensasi terpisah setelah persetujuan platform.
"""
from django.core.exceptions import ValidationError
from django.db import models

from common.models import BaseAppModel
from modules.tenants.managers import TenantScopedModel
from modules.wallet.models import ImmutableRecord

CHARGE_STATUSES = ["PENDING", "POSTED", "VOID", "REFUNDED"]
PENDING_REASONS = ["", "INSUFFICIENT_FUNDS", "WALLET_UNAVAILABLE"]


class SaaSPriceVersion(BaseAppModel):
    """Tarif platform (bukan data tenant). Versi baru = baris baru, tidak diedit."""

    code = models.CharField(max_length=32, unique=True)
    unit_price_idr = models.PositiveBigIntegerField()
    effective_from = models.DateTimeField()

    class Meta:
        ordering = ["-effective_from"]
        constraints = [models.CheckConstraint(condition=models.Q(unit_price_idr__gt=0, unit_price_idr__lte=10_000_000), name="ck_saas_price_amount")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Versi tarif tidak dapat diubah; terbitkan versi baru.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Versi tarif tidak dapat dihapus.")


class SaaSCharge(TenantScopedModel, BaseAppModel):
    participant = models.ForeignKey("booking.BookingParticipant", on_delete=models.PROTECT, related_name="saas_charges")
    booking = models.ForeignKey("booking.Booking", on_delete=models.PROTECT, related_name="saas_charges")
    source_payment = models.ForeignKey("payments.TravelPayment", on_delete=models.PROTECT, related_name="saas_charges")
    charge_type = models.CharField(max_length=16, default="initial", editable=False)
    unit_price_idr = models.PositiveBigIntegerField()
    price_version = models.ForeignKey(SaaSPriceVersion, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, default="PENDING", choices=[(s, s) for s in CHARGE_STATUSES])
    pending_reason = models.CharField(max_length=32, blank=True, choices=[(s, s or "-") for s in PENDING_REASONS])
    eligible_at = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True)
    wallet = models.ForeignKey("wallet.Wallet", null=True, on_delete=models.PROTECT, related_name="charges")
    ledger_entry = models.OneToOneField("wallet.WalletLedger", null=True, on_delete=models.PROTECT, related_name="charge")
    charged_at = models.DateTimeField(null=True)
    void_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-eligible_at", "-id"]
        indexes = [models.Index(fields=["tenant", "status", "eligible_at"], name="ix_saas_charge_fifo")]
        constraints = [
            # Spec §5.3 uq_saas_charge_once: VOID (belum pernah diposting) membuka epoch baru.
            models.UniqueConstraint(fields=["tenant", "participant"], condition=models.Q(charge_type="initial") & ~models.Q(status="VOID"), name="uq_saas_charge_once"),
            models.CheckConstraint(condition=models.Q(charge_type="initial"), name="ck_saas_charge_type"),
            models.CheckConstraint(condition=models.Q(unit_price_idr__gt=0), name="ck_saas_charge_amount"),
            models.CheckConstraint(condition=models.Q(status__in=CHARGE_STATUSES), name="ck_saas_charge_status"),
            models.CheckConstraint(
                condition=(
                    models.Q(status__in=["POSTED", "REFUNDED"], ledger_entry__isnull=False, wallet__isnull=False, charged_at__isnull=False, pending_reason="")
                    | models.Q(status__in=["PENDING", "VOID"], ledger_entry__isnull=True, charged_at__isnull=True)
                ),
                name="ck_saas_charge_posting",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            allowed = {"status", "pending_reason", "attempts", "last_attempt_at", "wallet", "ledger_entry", "charged_at", "void_reason", "updated_at"}
            if not kwargs.get("update_fields") or not set(kwargs["update_fields"]) <= allowed:
                raise ValidationError("Tarif dan peserta charge tidak dapat diubah.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Charge SaaS tidak dapat dihapus.")


class SaaSAdjustment(TenantScopedModel, BaseAppModel):
    """Kredit kompensasi atas charge POSTED (Spec §5.3 saas_adjustments, §7.5)."""

    charge = models.ForeignKey(SaaSCharge, on_delete=models.PROTECT, related_name="adjustments")
    kind = models.CharField(max_length=16, default="CREDIT", editable=False)
    amount_idr = models.PositiveBigIntegerField()
    status = models.CharField(max_length=16, default="REQUESTED", choices=[(s, s) for s in ["REQUESTED", "APPROVED", "REJECTED"]])
    reason = models.TextField()
    requested_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="saas_adjustment_requests")
    approver = models.ForeignKey("identity.User", null=True, on_delete=models.PROTECT, related_name="saas_adjustment_decisions")
    decision_reason = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True)
    ledger_entry = models.OneToOneField("wallet.WalletLedger", null=True, on_delete=models.PROTECT, related_name="adjustment")

    class Meta:
        ordering = ["-created_at", "-id"]
        permissions = [("approve_adjustment", "Approve SaaS charge refund credits")]
        constraints = [
            models.UniqueConstraint(fields=["charge"], condition=models.Q(status__in=["REQUESTED", "APPROVED"]), name="uq_saas_adjustment_open"),
            models.CheckConstraint(condition=models.Q(kind="CREDIT", amount_idr__gt=0), name="ck_saas_adjustment_credit"),
            models.CheckConstraint(
                condition=(
                    models.Q(status="APPROVED", ledger_entry__isnull=False, approver__isnull=False, decided_at__isnull=False)
                    | models.Q(status="REJECTED", ledger_entry__isnull=True, approver__isnull=False, decided_at__isnull=False)
                    | models.Q(status="REQUESTED", ledger_entry__isnull=True, approver__isnull=True, decided_at__isnull=True)
                ),
                name="ck_saas_adjustment_decision",
            ),
            models.CheckConstraint(condition=~models.Q(approver=models.F("requested_by")), name="ck_saas_adjustment_separation"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            allowed = {"status", "approver", "decision_reason", "decided_at", "ledger_entry", "updated_at"}
            if not kwargs.get("update_fields") or not set(kwargs["update_fields"]) <= allowed:
                raise ValidationError("Nominal dan alasan permintaan refund tidak dapat diubah.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Riwayat refund tidak dapat dihapus.")


class BillingEvent(ImmutableRecord):
    """Outbox durable billing; pengiriman notifikasi oleh worker S16."""

    kind = models.CharField(max_length=48)
    dedupe_key = models.CharField(max_length=160)
    payload_json = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "dedupe_key"], name="uq_billing_event_dedupe")]
