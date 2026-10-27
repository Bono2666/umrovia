"""Portal jamaah (S14, Spec §7.6, §8.4): undangan sekali pakai dan grant akses.

`PortalAccess` adalah tabel platform berisi ID saja (tanpa PII) agar request
portal — yang tidak membawa membership tenant — dapat masuk ke konteks RLS
tenant yang benar. Setiap query portal tetap disaring ke `pilgrim_id` grant.
"""
from django.db import models

from common.models import BaseAppModel
from modules.tenants.managers import TenantScopedModel


class PortalAccessStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Aktif"
    REVOKED = "REVOKED", "Dicabut"


class PortalAccess(BaseAppModel):
    user = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="portal_accesses")
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="portal_accesses")
    pilgrim_id = models.UUIDField()
    environment = models.CharField(max_length=16)
    status = models.CharField(max_length=16, choices=PortalAccessStatus.choices, default=PortalAccessStatus.ACTIVE)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "pilgrim_id"], name="uq_portal_access_user_pilgrim")]
        indexes = [models.Index(fields=["tenant", "pilgrim_id"], name="ix_portal_access_pilgrim")]


class PortalInvite(TenantScopedModel, BaseAppModel):
    """Undangan berbasis token: hanya SHA-256 yang disimpan; token = `<tenant>.<acak>`."""

    pilgrim = models.ForeignKey("pilgrims.Pilgrim", on_delete=models.CASCADE, related_name="portal_invites")
    environment = models.CharField(max_length=16)
    email = models.EmailField()
    token_sha256 = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey("identity.User", null=True, on_delete=models.SET_NULL, related_name="sent_portal_invites")
    accepted_by = models.ForeignKey("identity.User", null=True, on_delete=models.SET_NULL, related_name="accepted_portal_invites")

    class Meta:
        ordering = ["-created_at"]

    @property
    def open(self):
        from django.utils import timezone

        return self.used_at is None and self.revoked_at is None and self.expires_at > timezone.now()


class Announcement(TenantScopedModel, BaseAppModel):
    """POR-05: pengumuman travel di portal jamaah — semua jamaah atau satu keberangkatan."""

    environment = models.CharField(max_length=16)
    title = models.CharField(max_length=160)
    body = models.TextField()
    departure = models.ForeignKey("departures.Departure", null=True, blank=True, on_delete=models.CASCADE, related_name="announcements")
    published_at = models.DateTimeField(null=True, blank=True)  # kosong = draf
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey("identity.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-published_at", "-created_at"]


class ChangeRequestStatus(models.TextChoices):
    PENDING = "PENDING", "Menunggu verifikasi"
    APPROVED = "APPROVED", "Disetujui"
    REJECTED = "REJECTED", "Ditolak"


class ProfileChangeRequest(TenantScopedModel, BaseAppModel):
    """POR-06: permintaan koreksi identitas dari portal, diverifikasi admin travel.

    Nilai baru (bisa memuat NIK/paspor) disimpan terenkripsi; tampilan memakai
    `preview_json` yang sudah dimask. Diterapkan ke data jamaah hanya saat disetujui.
    """

    environment = models.CharField(max_length=16)
    pilgrim = models.ForeignKey("pilgrims.Pilgrim", on_delete=models.CASCADE, related_name="change_requests")
    requested_by = models.ForeignKey("identity.User", null=True, on_delete=models.SET_NULL, related_name="+")
    fields = models.JSONField(default=list)
    payload_encrypted = models.TextField()
    preview_json = models.JSONField(default=dict)
    reason = models.CharField(max_length=500)
    status = models.CharField(max_length=16, choices=ChangeRequestStatus.choices, default=ChangeRequestStatus.PENDING)
    decided_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["pilgrim"], condition=models.Q(status="PENDING"), name="uq_change_request_pending")]
