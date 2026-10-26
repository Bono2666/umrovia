"""Prepaid SaaS funds. No demo rows and no travel payment money here."""
from django.core.exceptions import ValidationError
from django.db import models

from common.models import BaseAppModel
from modules.tenants.managers import TenantScopedModel

MAX_BALANCE = 9_000_000_000_000_000  # exact in JavaScript as well as PostgreSQL bigint


class Wallet(TenantScopedModel, BaseAppModel):
    currency = models.CharField(max_length=3, default="IDR", editable=False)
    status = models.CharField(max_length=16, default="ACTIVE", choices=[("ACTIVE", "Aktif"), ("FROZEN", "Dibekukan")])
    balance_cached_idr = models.PositiveBigIntegerField(default=0)
    version = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "currency"], name="uq_wallet_tenant_currency"),
            models.CheckConstraint(condition=models.Q(currency="IDR"), name="ck_wallet_idr"),
            models.CheckConstraint(condition=models.Q(balance_cached_idr__lte=MAX_BALANCE), name="ck_wallet_balance_max"),
            models.CheckConstraint(condition=models.Q(status__in=["ACTIVE", "FROZEN"]), name="ck_wallet_status"),
        ]


class ImmutableRecord(TenantScopedModel, BaseAppModel):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Rekaman finansial bersifat append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Rekaman finansial tidak dapat dihapus.")


class WalletLedger(ImmutableRecord):
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="ledger")
    sequence = models.PositiveBigIntegerField()
    kind = models.CharField(max_length=16, choices=[("TOPUP", "Top-up"), ("DEBIT", "Debit SaaS"), ("REFUND", "Refund SaaS")])
    signed_amount_idr = models.BigIntegerField()
    balance_after_idr = models.PositiveBigIntegerField()
    reference_type = models.CharField(max_length=32)
    reference_id = models.UUIDField()
    description = models.CharField(max_length=240)
    actor = models.ForeignKey("identity.User", null=True, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-sequence"]
        constraints = [
            models.UniqueConstraint(fields=["wallet", "sequence"], name="uq_wallet_ledger_sequence"),
            models.UniqueConstraint(fields=["wallet", "kind", "reference_type", "reference_id"], name="uq_wallet_ledger_source"),
            models.CheckConstraint(condition=(models.Q(kind="TOPUP", signed_amount_idr__gt=0, reference_type="wallet_topup") | models.Q(kind="DEBIT", signed_amount_idr__lt=0, reference_type="saas_charge") | models.Q(kind="REFUND", signed_amount_idr__gt=0, reference_type="saas_adjustment")), name="ck_wallet_ledger_sign"),
            models.CheckConstraint(condition=models.Q(balance_after_idr__lte=MAX_BALANCE), name="ck_wallet_ledger_max"),
            models.CheckConstraint(condition=models.Q(sequence__gt=0), name="ck_wallet_sequence_positive"),
        ]


class WalletTopup(TenantScopedModel, BaseAppModel):
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="topups")
    amount_idr = models.PositiveBigIntegerField()
    provider = models.CharField(max_length=24, default="manual", choices=[("manual", "Transfer manual"), ("midtrans", "Midtrans")])
    status = models.CharField(max_length=16, default="CREATED", choices=[(s, s) for s in ["CREATED", "PENDING", "PAID", "EXPIRED", "REJECTED"]])
    instructions_json = models.JSONField(default=dict)
    payment_reference = models.CharField(max_length=120, blank=True)
    evidence_ref = models.CharField(max_length=512, blank=True)
    provider_txn_id = models.CharField(max_length=160, blank=True)
    requested_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="wallet_topup_requests")
    settled_by = models.ForeignKey("identity.User", null=True, on_delete=models.PROTECT, related_name="wallet_topup_settlements")
    expires_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True)
    reason = models.TextField(blank=True)
    ledger_entry = models.OneToOneField(WalletLedger, on_delete=models.PROTECT, null=True)
    # Midtrans Snap: redirect URL for the payer and the last authoritative status.
    payment_url = models.URLField(max_length=255, blank=True)
    gateway_status = models.CharField(max_length=32, blank=True)
    payment_type = models.CharField(max_length=32, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        permissions = [("settle_topup", "Verify platform settlement of SaaS wallet top-ups")]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_idr__gt=0, amount_idr__lte=10_000_000_000), name="ck_wallet_topup_amount"),
            models.CheckConstraint(condition=models.Q(provider__in=["manual", "midtrans"]), name="ck_wallet_topup_provider"),
            models.UniqueConstraint(fields=["provider", "provider_txn_id"], condition=~models.Q(provider_txn_id=""), name="uq_wallet_topup_provider_txn"),
            # Manual settlement needs a platform officer; Midtrans PAID is verified by the gateway.
            models.CheckConstraint(condition=(models.Q(status="PAID", ledger_entry__isnull=False, paid_at__isnull=False) & (models.Q(settled_by__isnull=False) | models.Q(provider="midtrans")) | models.Q(status__in=["CREATED", "PENDING", "EXPIRED", "REJECTED"], ledger_entry__isnull=True, paid_at__isnull=True)), name="ck_wallet_topup_settlement"),
            models.CheckConstraint(condition=~models.Q(settled_by=models.F("requested_by")), name="ck_wallet_topup_separation"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            allowed = {"status", "payment_reference", "evidence_ref", "provider_txn_id", "settled_by", "paid_at", "reason", "ledger_entry", "payment_url", "gateway_status", "payment_type", "updated_at"}
            if not kwargs.get("update_fields") or not set(kwargs["update_fields"]) <= allowed:
                raise ValidationError("Nominal dan instruksi top-up tidak dapat diubah.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Riwayat top-up tidak dapat dihapus.")


class GatewayOrder(BaseAppModel):
    """Platform lookup: gateway order → tenant/top-up. Webhooks arrive without
    a session, and wallet tables are RLS-scoped, so the tenant is resolved here
    first. No pilgrim or payer data; append-only."""

    provider = models.CharField(max_length=24, default="midtrans")
    order_id = models.CharField(max_length=50, unique=True)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="gateway_orders")
    topup_id = models.UUIDField(unique=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Pemetaan order gateway bersifat append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Pemetaan order gateway tidak dapat dihapus.")


class WalletOperation(ImmutableRecord):
    key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    topup = models.ForeignKey(WalletTopup, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="uq_wallet_operation_key")]


class WalletEvent(ImmutableRecord):
    topup = models.OneToOneField(WalletTopup, on_delete=models.PROTECT)
    kind = models.CharField(max_length=48, default="wallet.topup.paid")
    payload_json = models.JSONField(default=dict)


class WalletReconciliation(ImmutableRecord):
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="reconciliations")
    cached_balance_idr = models.PositiveBigIntegerField()
    ledger_balance_idr = models.BigIntegerField()
    variance_idr = models.BigIntegerField()
    ledger_count = models.PositiveBigIntegerField()
    consistent = models.BooleanField()
    details_json = models.JSONField(default=dict)
