"""Dana travel S11; nominal integer rupiah, terpisah dari wallet SaaS."""
from django.core.exceptions import ValidationError
from django.db import models

from common.models import BaseAppModel
from modules.tenants.managers import TenantScopedModel


class FinancialSequence(TenantScopedModel, BaseAppModel):
    environment = models.CharField(max_length=16)
    kind = models.CharField(max_length=16)
    year = models.PositiveIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "environment", "kind", "year"], name="uq_financial_sequence")]


class TravelInvoice(TenantScopedModel, BaseAppModel):
    environment = models.CharField(max_length=16)
    booking = models.OneToOneField("booking.Booking", on_delete=models.PROTECT, related_name="invoice")
    invoice_number = models.CharField(max_length=64)
    status = models.CharField(max_length=24, default="ISSUED", choices=[(s, s) for s in ["ISSUED", "PARTIALLY_PAID", "PAID", "VOIDED"]])
    issue_at = models.DateTimeField()
    due_at = models.DateField()
    total_idr = models.PositiveBigIntegerField()
    balance_idr = models.PositiveBigIntegerField()
    version = models.PositiveIntegerField(default=1)
    snapshot_json = models.JSONField(default=dict)
    pdf_data = models.BinaryField()
    checksum = models.CharField(max_length=64)
    issued_by = models.ForeignKey("identity.User", on_delete=models.SET_NULL, null=True, related_name="issued_travel_invoices")
    void_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-issue_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "environment", "invoice_number"], name="uq_travel_invoice_number"),
            models.CheckConstraint(condition=models.Q(balance_idr__lte=models.F("total_idr")), name="ck_invoice_balance"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            allowed = {"status", "balance_idr", "void_reason", "updated_at"}
            if not kwargs.get("update_fields") or not set(kwargs["update_fields"]) <= allowed:
                raise ValidationError("Snapshot invoice terbit tidak dapat diubah.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Invoice terbit tidak dapat dihapus.")


class InvoiceLine(TenantScopedModel, BaseAppModel):
    environment = models.CharField(max_length=16)
    invoice = models.ForeignKey(TravelInvoice, on_delete=models.PROTECT, related_name="lines")
    participant = models.ForeignKey("booking.BookingParticipant", on_delete=models.PROTECT)
    description = models.TextField()
    amount_idr = models.PositiveBigIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["invoice", "participant"], name="uq_invoice_participant_line")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Baris invoice terbit bersifat immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Baris invoice terbit tidak dapat dihapus.")


class TravelPayment(TenantScopedModel, BaseAppModel):
    environment = models.CharField(max_length=16)
    booking = models.ForeignKey("booking.Booking", on_delete=models.PROTECT, related_name="payments")
    invoice = models.ForeignKey(TravelInvoice, on_delete=models.PROTECT, related_name="payments")
    amount_idr = models.PositiveBigIntegerField()
    kind = models.CharField(max_length=16, choices=[("DP", "DP"), ("INSTALLMENT", "Cicilan"), ("BALANCE", "Pelunasan")])
    method = models.CharField(max_length=16, choices=[("TRANSFER", "Transfer bank"), ("CASH", "Tunai")])
    received_at = models.DateTimeField()
    bank_account = models.ForeignKey("travel_finance.TravelBankAccount", on_delete=models.PROTECT, null=True, blank=True)
    reference = models.CharField(max_length=120, blank=True)
    evidence_ref = models.CharField(max_length=512, blank=True)
    status = models.CharField(max_length=16, default="DRAFT", choices=[(s, s) for s in ["DRAFT", "SUBMITTED", "VERIFIED", "REJECTED", "REVERSED"]])
    created_by = models.ForeignKey("identity.User", on_delete=models.SET_NULL, null=True, related_name="recorded_travel_payments")
    verified_by = models.ForeignKey("identity.User", on_delete=models.SET_NULL, null=True, related_name="verified_travel_payments")
    verified_at = models.DateTimeField(null=True)
    reason = models.TextField(blank=True)
    verification_note = models.TextField(blank=True)
    eligibility_policy_json = models.JSONField(default=dict)
    simulated = models.BooleanField(default=False)

    class Meta:
        ordering = ["-received_at", "-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount_idr__gt=0), name="ck_payment_positive"),
            models.UniqueConstraint(fields=["tenant", "environment", "reference"], condition=~models.Q(reference=""), name="uq_payment_reference"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            allowed = {"status", "verified_by", "verified_at", "reason", "verification_note", "eligibility_policy_json", "updated_at"}
            if self.status == "DRAFT":
                allowed |= {"reference", "evidence_ref"}
            if not kwargs.get("update_fields") or not set(kwargs["update_fields"]) <= allowed:
                raise ValidationError("Nominal dan rincian pembayaran tidak dapat diubah; buat koreksi terpisah.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Pembayaran tidak dapat dihapus; gunakan penolakan atau reversal.")


class PaymentAllocation(TenantScopedModel, BaseAppModel):
    environment = models.CharField(max_length=16)
    payment = models.ForeignKey(TravelPayment, on_delete=models.PROTECT, related_name="allocations")
    invoice = models.ForeignKey(TravelInvoice, on_delete=models.PROTECT)
    participant = models.ForeignKey("booking.BookingParticipant", on_delete=models.PROTECT, related_name="payment_allocations")
    amount_idr = models.PositiveBigIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["payment", "participant"], name="uq_payment_participant_allocation"),
            models.CheckConstraint(condition=models.Q(amount_idr__gt=0), name="ck_allocation_positive"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Alokasi pembayaran bersifat immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Alokasi pembayaran tidak dapat dihapus.")


class TravelReceipt(TenantScopedModel, BaseAppModel):
    environment = models.CharField(max_length=16)
    payment = models.OneToOneField(TravelPayment, on_delete=models.PROTECT, related_name="receipt")
    receipt_no = models.CharField(max_length=64)
    issued_at = models.DateTimeField()
    status = models.CharField(max_length=16, default="ISSUED", choices=[("ISSUED", "Issued"), ("REVERSED", "Reversed")])
    snapshot_json = models.JSONField(default=dict)
    pdf_data = models.BinaryField()
    checksum = models.CharField(max_length=64)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "environment", "receipt_no"], name="uq_travel_receipt_number")]

    def save(self, *args, **kwargs):
        if not self._state.adding and set(kwargs.get("update_fields") or []) != {"status", "updated_at"}:
            raise ValidationError("Snapshot kuitansi tidak dapat diubah.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Kuitansi tidak dapat dihapus.")


class PaymentEvent(TenantScopedModel, BaseAppModel):
    """Outbox durable; worker pengiriman dan SaaS charge menyusul S12–S16."""
    environment = models.CharField(max_length=16)
    payment = models.ForeignKey(TravelPayment, on_delete=models.PROTECT, related_name="events")
    kind = models.CharField(max_length=48)
    payload_json = models.JSONField(default=dict)
    processed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["payment", "kind"], name="uq_payment_event")]


class PaymentOperation(TenantScopedModel, BaseAppModel):
    environment = models.CharField(max_length=16)
    action = models.CharField(max_length=24)
    key = models.CharField(max_length=128)
    request_hash = models.CharField(max_length=64)
    response_json = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "environment", "action", "key"], name="uq_payment_operation")]
