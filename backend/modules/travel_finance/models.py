"""Keuangan travel — rekening bank tenant (Spec §5.3 `travel_bank_accounts`).

Keamanan (§5.3 account_masked): nomor rekening ASLI tidak pernah disimpan —
hanya `account_masked` (mis. `************1234`) + nama pemilik. Tabel ini
milik tenant (bukan dana SaaS, POL-05) dan termasuk data bisnis — wajib
di-RLS-kan mengikuti ADR-0003 §3 sejak tabel ini ada.
"""
from django.core.exceptions import ValidationError
from django.db import models

from common.models import BaseAppModel
from modules.tenants.managers import TenantScopedModel


def mask_account_number(account_number: str) -> str:
    """Simpan maksimal 4 digit terakhir — sisanya asterisk."""
    digits = "".join(ch for ch in account_number if ch.isalnum())
    if len(digits) <= 4:
        return "*" * max(len(digits), 1)
    return "*" * (len(digits) - 4) + digits[-4:]


class TravelBankAccount(TenantScopedModel, BaseAppModel):
    """Rekening bank milik travel (tenant-only, §5.3; FK `tenant` dari base)."""

    bank_name = models.CharField(max_length=100)
    account_name = models.CharField(max_length=160)
    account_masked = models.CharField(max_length=32)
    active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "rekening bank"
        verbose_name_plural = "rekening bank"
        ordering = ["bank_name", "account_masked"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "bank_name", "account_masked"], name="uq_bank_account_masked"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.bank_name} {self.account_masked}"


class ExpenseCategory(models.TextChoices):
    TICKET = "TICKET", "Tiket pesawat"
    HOTEL = "HOTEL", "Hotel"
    VISA = "VISA", "Visa & dokumen"
    TRANSPORT = "TRANSPORT", "Transportasi darat"
    CATERING = "CATERING", "Konsumsi"
    GUIDE = "GUIDE", "Muthawif & tour leader"
    EQUIPMENT = "EQUIPMENT", "Perlengkapan jamaah"
    MARKETING = "MARKETING", "Pemasaran"
    COMMISSION = "COMMISSION", "Komisi agen"
    OFFICE = "OFFICE", "Operasional kantor"
    OTHER = "OTHER", "Lainnya"


class TravelExpense(TenantScopedModel, BaseAppModel):
    """Pengeluaran travel (S17, RPT-02): kas keluar per rekening/kategori/keberangkatan.

    Catatan keuangan tidak diedit; koreksi dengan membatalkan (alasan wajib)
    lalu mencatat ulang. Bukan dana SaaS wallet (POL-05).
    """

    environment = models.CharField(max_length=16)
    spent_on = models.DateField()
    category = models.CharField(max_length=16, choices=ExpenseCategory.choices)
    amount_idr = models.PositiveBigIntegerField()
    departure = models.ForeignKey("departures.Departure", null=True, blank=True, on_delete=models.PROTECT, related_name="expenses")
    bank_account = models.ForeignKey(TravelBankAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="expenses")
    description = models.CharField(max_length=240)
    reference = models.CharField(max_length=120, blank=True, default="")
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=240, blank=True, default="")
    created_by = models.ForeignKey("identity.User", null=True, on_delete=models.SET_NULL, related_name="+")
    voided_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    branch = models.ForeignKey("tenants.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="expenses")
    payee = models.CharField(max_length=160, blank=True, default="")  # penerima dana (MOD-11)
    # Maker-checker (MOD-11): bila diaktifkan, pengeluaran baru PENDING sampai disetujui staf lain.
    approval_status = models.CharField(max_length=16, choices=[("APPROVED", "Disetujui"), ("PENDING", "Menunggu persetujuan"), ("REJECTED", "Ditolak")], default="APPROVED")
    approved_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=240, blank=True, default="")
    evidence_key = models.CharField(max_length=300, blank=True, default="")  # lampiran bukti (privat)

    class Meta:
        ordering = ["-spent_on", "-created_at"]
        indexes = [models.Index(fields=["tenant", "environment", "spent_on"], name="ix_expense_period")]
        constraints = [models.CheckConstraint(condition=models.Q(amount_idr__gt=0), name="ck_expense_positive")]

    def save(self, *args, **kwargs):
        fields = set(kwargs.get("update_fields") or [])
        mutable = {"voided_at", "void_reason", "voided_by", "approval_status", "approved_by", "approved_at", "rejection_reason", "evidence_key", "updated_at"}
        if not self._state.adding and (not fields or not fields <= mutable):
            raise ValidationError("Pengeluaran tidak dapat diubah; batalkan lalu catat ulang.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Pengeluaran tidak dapat dihapus; gunakan pembatalan.")


class OpeningBalance(TenantScopedModel, BaseAppModel):
    """Saldo awal rekening/kas tunai (MOD-11). `bank_account` kosong = kas tunai.

    Saldo awal pertama langsung berlaku. Koreksi berikutnya menunggu
    persetujuan (`bank_accounts.approve`) dan, bila disetujui, menggantikan
    saldo awal sebelumnya (riwayat tetap tersimpan).
    """

    environment = models.CharField(max_length=16)
    bank_account = models.ForeignKey(TravelBankAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="opening_balances")
    as_of = models.DateField()
    amount_idr = models.BigIntegerField()
    reason = models.CharField(max_length=240, blank=True, default="")
    status = models.CharField(max_length=16, choices=[("APPROVED", "Berlaku"), ("PENDING", "Menunggu persetujuan"), ("REJECTED", "Ditolak"), ("SUPERSEDED", "Digantikan")], default="PENDING")
    created_by = models.ForeignKey("identity.User", null=True, on_delete=models.SET_NULL, related_name="+")
    decided_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=240, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "environment", "bank_account"], condition=models.Q(status="APPROVED"), name="uq_opening_balance_active_account"),
            models.UniqueConstraint(fields=["tenant", "environment"], condition=models.Q(status="APPROVED", bank_account__isnull=True), name="uq_opening_balance_active_cash"),
        ]


class CashTransfer(TenantScopedModel, BaseAppModel):
    """Transfer antarrekening/kas (MOD-11): satu catatan = pasangan keluar/masuk,
    sehingga total kas perusahaan tidak berubah. Koreksi dengan pembatalan."""

    environment = models.CharField(max_length=16)
    transferred_on = models.DateField()
    from_account = models.ForeignKey(TravelBankAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="transfers_out")
    to_account = models.ForeignKey(TravelBankAccount, null=True, blank=True, on_delete=models.PROTECT, related_name="transfers_in")
    amount_idr = models.PositiveBigIntegerField()
    description = models.CharField(max_length=240, blank=True, default="")
    reference = models.CharField(max_length=120, blank=True, default="")
    branch = models.ForeignKey("tenants.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_by = models.ForeignKey("identity.User", null=True, on_delete=models.SET_NULL, related_name="+")
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=240, blank=True, default="")
    voided_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-transferred_on", "-created_at"]
        constraints = [models.CheckConstraint(condition=models.Q(amount_idr__gt=0), name="ck_transfer_positive")]

    def save(self, *args, **kwargs):
        fields = set(kwargs.get("update_fields") or [])
        if not self._state.adding and (not fields or not fields <= {"voided_at", "void_reason", "voided_by", "updated_at"}):
            raise ValidationError("Transfer tidak dapat diubah; batalkan lalu catat ulang.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Transfer tidak dapat dihapus; gunakan pembatalan.")
