"""Master paket perjalanan (Spec §5.2 `packages`, PRD MOD-05).

Aturan:
- Tabel bisnis tenant+environment → RLS sejak migrasi pertama (ADR-0003 §3,
  pola §5.6 + NULLIF fail-closed).
- `code` auto `PKT-<8hex>`, UNIQUE(tenant, environment, code) — §5.2
  "UNIQUE composite code"; tidak global-unique lintas tenant.
- Harga dasar integer rupiah nonnegatif & terbatas (§10.1); perubahan harga
  paket TIDAK menyentuh invoice existing — snapshot di booking (MOD-05, S09).
- `published` = siap ditampilkan/dipesan (kolom esensial §5.2); `status`
  = lifecycle MOD-05 (DRAFT/ACTIVE/INACTIVE/ARCHIVED). Publish hanya sah
  dari status ACTIVE (divalidasi serializer).
- Varian harga per tipe kamar/dewasa-anak-bayi → menyusul S09 (snapshot
  harga per booking_participant, §5.2 booking_price_lines).
"""
import uuid

from django.db import models

from common.models import BaseAppModel
from modules.tenants.managers import TenantScopedModel


class PackageKind(models.TextChoices):
    UMROH = "umroh", "Umroh"
    HAJI = "haji", "Haji"
    ZIARAH = "ziarah", "Ziarah"


class PackageStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Aktif"
    INACTIVE = "INACTIVE", "Nonaktif"
    ARCHIVED = "ARCHIVED", "Diarsipkan"


class TravelPackage(TenantScopedModel, BaseAppModel):
    """Katalog paket travel (MOD-05) — tanpa delete keras setelah dipakai."""

    environment = models.CharField(
        max_length=16, choices=[("demo", "Demo"), ("production", "Produksi")]
    )
    code = models.CharField(max_length=32)  # auto PKT-<8hex>
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=16, choices=PackageKind.choices, default=PackageKind.UMROH)
    description = models.TextField(blank=True, default="")
    duration_days = models.PositiveIntegerField(default=0)
    price_idr = models.PositiveIntegerField(default=0)  # rupiah integer (§10.1)
    inclusions_json = models.JSONField(default=list, blank=True)  # fasilitas (MOD-05)
    exclusions_json = models.JSONField(default=list, blank=True)  # non-fasilitas
    cancellation_policy = models.TextField(blank=True, default="")
    payment_terms = models.TextField(blank=True, default="")
    status = models.CharField(max_length=16, choices=PackageStatus.choices, default=PackageStatus.DRAFT)
    published = models.BooleanField(default=False)  # kolom esensial §5.2

    class Meta:
        verbose_name = "paket"
        verbose_name_plural = "paket"
        ordering = ["name", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "environment", "code"], name="uq_package_code"
            ),
            models.CheckConstraint(
                condition=models.Q(price_idr__gte=0), name="ck_package_price_nonneg"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


def generate_package_code() -> str:
    """Kode paket auto, konsisten pola JM- jamaah (S07)."""
    return f"PKT-{uuid.uuid4().hex[:8].upper()}"
