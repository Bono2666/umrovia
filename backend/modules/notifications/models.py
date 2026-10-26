"""Notifikasi transaksi (S16, Spec §5.5, §11, NTF-01…05).

`Notification` adalah outbox transaksional sekaligus log pengiriman: baris
ditulis di transaksi yang sama dengan event bisnis, sehingga event tidak hilang
dan tidak terkirim bila transaksi gagal. Unique key `(source_key, template_key,
channel, penerima)` menjamin satu pesan logis per event meski diproses ulang.

`NotificationJob` adalah antrean platform berisi ID saja (pola GatewayOrder /
PortalAccess) agar worker dapat menemukan pekerjaan lintas tenant tanpa
melewati RLS tabel notifikasi.
"""
from django.db import models

from common.models import BaseAppModel
from modules.tenants.managers import TenantScopedModel


class Channel(models.TextChoices):
    EMAIL = "EMAIL", "Email"
    IN_APP = "IN_APP", "Portal"


class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", "Menunggu"
    SENT = "SENT", "Terkirim"
    FAILED = "FAILED", "Gagal, dicoba ulang"
    DEAD = "DEAD", "Gagal permanen"


class RecipientType(models.TextChoices):
    PILGRIM = "PILGRIM", "Jamaah"
    USER = "USER", "Pengguna travel"


class NotificationTemplate(TenantScopedModel, BaseAppModel):
    """Teks template milik travel; kosong = memakai teks bawaan. Versi naik tiap perubahan."""

    key = models.CharField(max_length=48)
    subject = models.CharField(max_length=200, blank=True, default="")
    body = models.TextField(blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    updated_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="uq_notification_template_key")]


class Notification(TenantScopedModel, BaseAppModel):
    environment = models.CharField(max_length=16)
    event_type = models.CharField(max_length=48)
    source_key = models.CharField(max_length=160)
    template_key = models.CharField(max_length=48)
    template_version = models.PositiveIntegerField(default=1)
    channel = models.CharField(max_length=16, choices=Channel.choices)
    recipient_type = models.CharField(max_length=16, choices=RecipientType.choices)
    recipient_id = models.UUIDField()
    recipient_name = models.CharField(max_length=160, blank=True, default="")
    recipient_email = models.EmailField(blank=True, default="")
    subject = models.CharField(max_length=240)
    body = models.TextField()
    status = models.CharField(max_length=16, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=80, blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    resend_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "source_key", "template_key", "channel", "recipient_type", "recipient_id"],
                name="uq_notification_dedupe",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "recipient_type", "recipient_id", "channel"], name="ix_notification_recipient"),
            models.Index(fields=["tenant", "status"], name="ix_notification_status"),
        ]


class NotificationJob(models.Model):
    """Antrean email: `id` = id notifikasi; baris dihapus saat SENT/DEAD."""

    id = models.UUIDField(primary_key=True)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="+")
    due_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
