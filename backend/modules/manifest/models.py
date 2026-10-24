"""Checklist dokumen operasional & versi manifest (Spec §5.2
`document_requirements` + `manifest_versions`, §6.5, §7.6, §8.3; PRD MOD-08
checklist, MOD-12 manifest).

Aturan:
- Tabel bisnis tenant+environment → RLS sejak migrasi pertama (ADR-0003 §3).
- `DocumentRequirement` = definisi checklist wajib per paket, atau global
  (bila `package` null) — spesifikasi per paket menimpa global per `kind`.
  `mandatory` + `deadline_rule` menggerakkan dua gerbang:
  - `before_ready` (default): keberangkatan → READY (§6.5, OPS02 dengan
    *approved exception*) dan booking → READY_TO_DEPART;
  - `before_departure`: keberangkatan → DEPARTED.
  Tanpa requirement yang berlaku, gerbang dianggap lengkap (belum ada yang
  bisa kurang — hook S08/S09 sebelumnya selalu True).
- `ManifestVersion` = snapshot daftar jamaah satu keberangkatan (§7.6
  "publish snapshot version"): `version_no` UNIK per departure, isi roster
  disimpan sebagai JSON di `snapshot_object_key` + `checksum` sha256 —
  append-only; revisi = versi baru (OPS-04 jejak perubahan).
- Kolom persis §5.2 (integrity: snapshot tidak diedit; baris manifest
  selalu dibangun ulang dari data sumber).
"""
from django.db import models

from common.models import BaseAppModel
from modules.pilgrims.models import PilgrimDocumentKind
from modules.tenants.managers import TenantScopedModel


class DocumentRequirementDeadline(models.TextChoices):
    """Kapan requirement dicek (gerbang transisi)."""

    BEFORE_READY = "before_ready", "Sebelum siap berangkat (READY)"
    BEFORE_DEPARTURE = "before_departure", "Sebelum keberangkatan (DEPARTED)"


class DocumentRequirement(TenantScopedModel, BaseAppModel):
    """Checklist dokumen wajib — global (package null) atau per paket (§5.2)."""

    environment = models.CharField(
        max_length=16, choices=[("demo", "Demo"), ("production", "Produksi")]
    )
    package = models.ForeignKey(
        "catalog.TravelPackage",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="document_requirements",
    )
    kind = models.CharField(max_length=16, choices=PilgrimDocumentKind.choices)
    mandatory = models.BooleanField(default=True)
    deadline_rule = models.CharField(
        max_length=24,
        choices=DocumentRequirementDeadline.choices,
        default=DocumentRequirementDeadline.BEFORE_READY,
    )

    class Meta:
        verbose_name = "syarat dokumen"
        verbose_name_plural = "syarat dokumen"
        ordering = ["kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "environment", "kind"],
                condition=models.Q(package__isnull=True),
                name="uq_docreq_global_kind",
            ),
            models.UniqueConstraint(
                fields=["tenant", "environment", "package", "kind"],
                condition=models.Q(package__isnull=False),
                name="uq_docreq_package_kind",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "environment", "kind"], name="ix_docreq_kind"
            ),
        ]

    def __str__(self) -> str:
        scope = self.package_id and self.package.code or "global"
        return f"{scope}:{self.kind} ({'wajib' if self.mandatory else 'opsional'})"


class ManifestVersion(TenantScopedModel, BaseAppModel):
    """Versi snapshot manifest keberangkatan (§5.2, append-only, OPS-04)."""

    environment = models.CharField(
        max_length=16, choices=[("demo", "Demo"), ("production", "Produksi")]
    )
    departure = models.ForeignKey(
        "departures.Departure",
        on_delete=models.PROTECT,
        related_name="manifest_versions",
    )
    version_no = models.PositiveIntegerField()
    published_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="published_manifests",
    )
    snapshot_object_key = models.CharField(max_length=512)
    checksum = models.CharField(max_length=64)  # sha256 hex isi snapshot

    class Meta:
        verbose_name = "versi manifest"
        verbose_name_plural = "versi manifest"
        ordering = ["-version_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["departure", "version_no"], name="uq_manifest_departure_version"
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "environment", "departure"],
                name="ix_manifest_departure",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.departure_id} v{self.version_no}"
