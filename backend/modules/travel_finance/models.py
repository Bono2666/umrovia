"""Keuangan travel — rekening bank tenant (Spec §5.3 `travel_bank_accounts`).

Keamanan (§5.3 account_masked): nomor rekening ASLI tidak pernah disimpan —
hanya `account_masked` (mis. `************1234`) + nama pemilik. Tabel ini
milik tenant (bukan dana SaaS, POL-05) dan termasuk data bisnis — wajib
di-RLS-kan mengikuti ADR-0003 §3 sejak tabel ini ada.
"""
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
