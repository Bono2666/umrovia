"""Audit event (Spec §5.5: actor/action/object/tenant/IP/redacted change summary).

Append-only — `save`/`delete` update & hapus ditolak (§13 Audit: "append-only
important financial/security actions"). Tabel kontrol-plane → tidak di-RLS-kan
(ADR-0003 §3); tenant diisi server-side dari context request.
"""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from modules.tenants.models import Tenant


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    action = models.CharField(max_length=100, db_index=True)  # mis. "memberships.invited"
    object_type = models.CharField(max_length=64, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    changes_json = models.JSONField(default=dict, blank=True)  # ringkasan perubahan (sudah di-redact)
    ip = models.GenericIPAddressField(null=True, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Audit event"
        ordering = ("-occurred_at",)
        indexes = [models.Index(fields=("tenant", "occurred_at"), name="ae_tenant_occurred_idx")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("audit_events bersifat append-only (Spec §5.5).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("audit_events bersifat append-only (Spec §5.5).")

    def __str__(self) -> str:
        return f"{self.action} @ {self.tenant_id or '-'}"
