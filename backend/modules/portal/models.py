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
