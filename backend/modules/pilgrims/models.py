"""Master jamaah + model dokumen teramankan (Spec §5.2, §8.3, §10.1; PRD MOD-04).

Aturan kunci:
- Tabel bisnis berkolom tenant_id + environment (S07+) → RLS sejak migrasi
  pertama (ADR-0003 §3, pola §5.6 + NULLIF fail-closed).
- NIK & nomor paspor disimpan TERENKRIPSI (`*_encrypted`, Fernet) — API hanya
  pernah mengirim varian masked (4 karakter terakhir); pencarian/duplikat
  memakai `identity_hash` (HMAC tenant-scoped) tanpa dekripsi (§5.2
  "search normalisasi aman; jangan global-unique identity").
- Identitas sama → ditandai `possible_duplicate_of`, BUKAN digabung otomatis
  (MOD-04: "identitas yang sama ditandai sebagai potensi duplikat, bukan
  otomatis digabung").
- `object_key` dokumen wajib ber-prefix tenant/environment (§5.2 integrity
  note) — divalidasi di serializer; signed URL baru setelah permission check.
"""
import uuid

from django.db import models

from common.models import BaseAppModel
from modules.tenants.managers import TenantScopedModel


class PilgrimGender(models.TextChoices):
    MALE = "male", "Laki-laki"
    FEMALE = "female", "Perempuan"


class PilgrimStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Aktif"
    ARCHIVED = "ARCHIVED", "Diarsipkan"


class Pilgrim(TenantScopedModel, BaseAppModel):
    """Master jamaah per tenant+environment (MOD-04, tanpa global-unique PII)."""

    environment = models.CharField(max_length=16, choices=[("demo", "Demo"), ("production", "Produksi")])
    code = models.CharField(max_length=32)  # auto JM-<8hex>, unik per tenant+environment
    name = models.CharField(max_length=160)  # nama sesuai dokumen
    gender = models.CharField(max_length=8, choices=PilgrimGender.choices, blank=True, default="")
    birth_date = models.DateField(null=True, blank=True)
    birth_place = models.CharField(max_length=120, blank=True, default="")
    nationality = models.CharField(max_length=64, blank=True, default="Indonesia")
    marital_status = models.CharField(max_length=16, blank=True, default="")
    address = models.TextField(blank=True, default="")
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")  # kanonis +62 (E.164 presentation)
    emergency_contact_name = models.CharField(max_length=160, blank=True, default="")
    emergency_contact_phone = models.CharField(max_length=32, blank=True, default="")
    guardian_name = models.CharField(max_length=160, blank=True, default="")  # wali/mahram bila relevan
    guardian_relation = models.CharField(max_length=64, blank=True, default="")
    special_needs = models.TextField(blank=True, default="")  # catatan kebutuhan khusus (akses terbatas)

    # --- PII sensitif: terenkripsi di rest, hanya masked yang keluar API (§10.1)
    identity_encrypted = models.TextField(blank=True, default="")  # NIK/KTP
    identity_masked = models.CharField(max_length=32, blank=True, default="")
    identity_hash = models.CharField(max_length=64, blank=True, default="")  # HMAC tenant-scoped (dedup)
    passport_encrypted = models.TextField(blank=True, default="")
    passport_masked = models.CharField(max_length=32, blank=True, default="")
    passport_name = models.CharField(max_length=160, blank=True, default="")
    passport_issued_at = models.DateField(null=True, blank=True)
    passport_expires_at = models.DateField(null=True, blank=True)
    passport_place_of_issue = models.CharField(max_length=120, blank=True, default="")

    status = models.CharField(max_length=16, choices=PilgrimStatus.choices, default=PilgrimStatus.ACTIVE)
    possible_duplicate_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="duplicates"
    )

    class Meta:
        verbose_name = "jamaah"
        verbose_name_plural = "jamaah"
        ordering = ["name", "code"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "environment", "code"], name="uq_pilgrim_code"),
        ]
        indexes = [
            models.Index(fields=["tenant", "environment", "identity_hash"], name="ix_pilgrim_identity"),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class PilgrimDocumentKind(models.TextChoices):
    KTP = "ktp", "KTP"
    PASSPORT = "passport", "Paspor"
    PHOTO = "photo", "Foto"
    KK = "kk", "Kartu Keluarga"
    OTHER = "other", "Dokumen lain"


class PilgrimDocumentStatus(models.TextChoices):
    UPLOADED = "UPLOADED", "Terunggah"
    UNDER_REVIEW = "UNDER_REVIEW", "Ditinjau"
    APPROVED = "APPROVED", "Disetujui"
    REJECTED = "REJECTED", "Ditolak"


class PilgrimDocument(TenantScopedModel, BaseAppModel):
    """Dokumen jamaah dengan object_key ber-namespace + versi (§5.2).

    Versi booking-participant FK (§5.2 `booking_participant_id`) menyusul S09
    saat tabel booking_participants ada; pada S07 dokumen melekat pada jamaah
    (PRD data model `pilgrim_documents`).
    """

    pilgrim = models.ForeignKey(Pilgrim, on_delete=models.CASCADE, related_name="documents")
    environment = models.CharField(max_length=16, choices=[("demo", "Demo"), ("production", "Produksi")])
    kind = models.CharField(max_length=16, choices=PilgrimDocumentKind.choices)
    object_key = models.CharField(max_length=512)  # prefix tenant/environment, divalidasi serializer
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=PilgrimDocumentStatus.choices, default=PilgrimDocumentStatus.UPLOADED)
    reviewed_by = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_pilgrim_documents"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")  # wajib saat REJECTED (UI-11)

    class Meta:
        verbose_name = "dokumen jamaah"
        verbose_name_plural = "dokumen jamaah"
        ordering = ["kind", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["pilgrim", "kind", "version"], name="uq_pilgrim_doc_kind_version"),
        ]

    def __str__(self) -> str:
        return f"{self.pilgrim_id} {self.kind} v{self.version} ({self.status})"


def generate_pilgrim_code() -> str:
    """Kode jamaah auto, murah dibaca staf (pola DEMO-<hex> §7.1)."""
    return f"JM-{uuid.uuid4().hex[:8].upper()}"
