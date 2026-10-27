"""Agen, referral & komisi (PRD MOD-10, P0).

- Master agen per environment; setiap booking punya paling banyak satu agen
  yang mendapat kredit penjualan, dengan histori perubahan (`BookingAgentChange`).
- Kebijakan komisi fixed per jamaah atau persentase dari harga bersih, per
  agen/paket/periode. Kebijakan yang berlaku DISNAPSHOT ke komisi saat booking
  direservasi; perubahan kebijakan berikutnya tidak mengubah komisi lama.
- Siklus: ESTIMATED → ELIGIBLE (syarat pembayaran tercapai) → APPROVED → PAID;
  REVERSED bila booking batal/agen diganti/koreksi. Pembayaran komisi
  mencatat pengeluaran kategori "Komisi agen" (kas keluar MOD-11).

Data tenant: RLS ENABLE+FORCE sejak tabel dibuat (ADR-0003).
"""
import secrets

from django.db import models

from common.models import BaseAppModel
from modules.tenants.managers import TenantScopedModel


def generate_agent_code() -> str:
    return f"AG-{secrets.token_hex(3).upper()}"


class Agent(TenantScopedModel, BaseAppModel):
    environment = models.CharField(max_length=16)
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=32, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    business_id = models.CharField(max_length=64, blank=True, default="")  # NIK/NPWP/NIB
    bank_name = models.CharField(max_length=100, blank=True, default="")
    bank_account_name = models.CharField(max_length=160, blank=True, default="")
    bank_account_masked = models.CharField(max_length=32, blank=True, default="")
    area = models.CharField(max_length=120, blank=True, default="")
    branch = models.ForeignKey("tenants.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="agents")
    level = models.CharField(max_length=40, blank=True, default="")
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name", "code"]
        constraints = [models.UniqueConstraint(fields=["tenant", "environment", "code"], name="uq_agent_code")]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class CommissionKind(models.TextChoices):
    FIXED_PER_PAX = "FIXED_PER_PAX", "Nominal tetap per jamaah"
    PERCENT_NET = "PERCENT_NET", "Persentase harga bersih"


class CommissionTrigger(models.TextChoices):
    DP_VERIFIED = "DP_VERIFIED", "Setelah DP terverifikasi"
    FULLY_PAID = "FULLY_PAID", "Setelah lunas"


class CommissionPolicy(TenantScopedModel, BaseAppModel):
    environment = models.CharField(max_length=16)
    name = models.CharField(max_length=120)
    agent = models.ForeignKey(Agent, null=True, blank=True, on_delete=models.PROTECT, related_name="policies")
    package = models.ForeignKey("catalog.TravelPackage", null=True, blank=True, on_delete=models.PROTECT, related_name="commission_policies")
    kind = models.CharField(max_length=16, choices=CommissionKind.choices)
    amount_idr = models.PositiveBigIntegerField(default=0)
    percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    trigger = models.CharField(max_length=16, choices=CommissionTrigger.choices, default=CommissionTrigger.DP_VERIFIED)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-active", "name"]


class BookingAgentChange(TenantScopedModel, BaseAppModel):
    environment = models.CharField(max_length=16)
    booking = models.ForeignKey("booking.Booking", on_delete=models.CASCADE, related_name="agent_changes")
    from_agent = models.ForeignKey(Agent, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    to_agent = models.ForeignKey(Agent, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    reason = models.CharField(max_length=240, blank=True, default="")
    changed_by = models.ForeignKey("identity.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]


class CommissionStatus(models.TextChoices):
    ESTIMATED = "ESTIMATED", "Estimasi"
    ELIGIBLE = "ELIGIBLE", "Layak dibayar"
    APPROVED = "APPROVED", "Disetujui"
    PAID = "PAID", "Dibayar"
    REVERSED = "REVERSED", "Dibatalkan"


class Commission(TenantScopedModel, BaseAppModel):
    environment = models.CharField(max_length=16)
    booking = models.ForeignKey("booking.Booking", on_delete=models.PROTECT, related_name="commissions")
    agent = models.ForeignKey(Agent, on_delete=models.PROTECT, related_name="commissions")
    policy = models.ForeignKey(CommissionPolicy, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    policy_snapshot_json = models.JSONField(default=dict)
    pax = models.PositiveIntegerField(default=0)
    basis_idr = models.PositiveBigIntegerField(default=0)
    amount_idr = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=16, choices=CommissionStatus.choices, default=CommissionStatus.ESTIMATED)
    eligible_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    paid_on = models.DateField(null=True, blank=True)
    paid_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    bank_account = models.ForeignKey("travel_finance.TravelBankAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    reference = models.CharField(max_length=120, blank=True, default="")
    expense = models.ForeignKey("travel_finance.TravelExpense", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")  # terisi = pembatalan manual
    reverse_reason = models.CharField(max_length=240, blank=True, default="")
    review_note = models.CharField(max_length=240, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["booking"], condition=~models.Q(status="REVERSED"), name="uq_active_commission_per_booking"),
        ]
        indexes = [models.Index(fields=["tenant", "environment", "status"], name="ix_commission_status")]
