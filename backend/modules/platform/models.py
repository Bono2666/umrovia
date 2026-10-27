"""Public website enquiries, separate from tenant operational data."""
import uuid

from django.db import models
from django.utils import timezone

from common.models import BaseAppModel


class ContactMessage(models.Model):
    class Topic(models.TextChoices):
        PRODUCT = "product", "Produk & demo"
        PRICING = "pricing", "Harga & pembayaran"
        SUPPORT = "support", "Bantuan penggunaan"
        PRIVACY = "privacy", "Privasi & data pribadi"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    company = models.CharField(max_length=200, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=32, blank=True)
    topic = models.CharField(max_length=16, choices=Topic.choices)
    message = models.TextField(max_length=4000)
    consented_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.id} — {self.get_topic_display()}"


# --------------------------------------------------------- S18 control plane --



class PlatformControl(models.Model):
    """Pemegang izin konsol platform (tanpa tabel). Izin diberikan lewat grup
    "Platform Super Admin" / "Platform Billing" / "Platform Support"; role tenant
    tidak pernah memberi izin ini."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("console_view", "View platform console (metadata and aggregates, no pilgrim data)"),
            ("tenant_manage", "Suspend, reactivate, terminate tenants and extend trials"),
            ("pricing_manage", "Publish SaaS price versions"),
            ("audit_view", "View redacted platform-wide audit trail"),
            ("support_manage", "Handle tenant support tickets"),
        ]


class StaffMFA(BaseAppModel):
    """TOTP (RFC 6238) wajib untuk staf platform. Secret dienkripsi; kode pemulihan disimpan sebagai SHA-256."""

    user = models.OneToOneField("identity.User", on_delete=models.CASCADE, related_name="platform_mfa")
    secret_encrypted = models.TextField()
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_used_step = models.BigIntegerField(default=0)
    recovery_hashes = models.JSONField(default=list, blank=True)


class TenantLifecycleRequest(BaseAppModel):
    """Aksi kritis dua orang (UI-19): pengakhiran tenant diajukan satu admin, diputuskan admin lain."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Menunggu persetujuan"
        APPROVED = "APPROVED", "Disetujui"
        REJECTED = "REJECTED", "Ditolak"

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="lifecycle_requests")
    kind = models.CharField(max_length=16, default="TERMINATE")
    reason = models.CharField(max_length=240)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    requested_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    decided_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    decision_reason = models.CharField(max_length=240, blank=True, default="")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["tenant", "kind"], condition=models.Q(status="PENDING"), name="uq_lifecycle_pending")]


class SupportTicket(BaseAppModel):
    """Tiket dukungan tenant ↔ platform. Tabel platform: tenant hanya melihat tiketnya
    (filter server-side), staf Support hanya melihat tiket — bukan data operasional tenant."""

    class Category(models.TextChoices):
        ACCOUNT = "ACCOUNT", "Akun & akses"
        BILLING = "BILLING", "SaaS Wallet & tagihan"
        TECHNICAL = "TECHNICAL", "Kendala teknis"
        DATA = "DATA", "Data & privasi"
        OTHER = "OTHER", "Lainnya"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Terbuka"
        IN_PROGRESS = "IN_PROGRESS", "Diproses"
        WAITING_TENANT = "WAITING_TENANT", "Menunggu travel"
        RESOLVED = "RESOLVED", "Selesai"

    number = models.CharField(max_length=24, unique=True)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.PROTECT, related_name="support_tickets")
    opened_by = models.ForeignKey("identity.User", null=True, on_delete=models.SET_NULL, related_name="+")
    subject = models.CharField(max_length=160)
    category = models.CharField(max_length=16, choices=Category.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=8, choices=[("NORMAL", "Normal"), ("HIGH", "Tinggi")], default="NORMAL")
    assigned_to = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    last_message_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_message_at"]
        indexes = [models.Index(fields=["tenant", "status"], name="ix_support_tenant_status")]


class SupportMessage(BaseAppModel):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey("identity.User", null=True, on_delete=models.SET_NULL, related_name="+")
    from_platform = models.BooleanField(default=False)
    internal = models.BooleanField(default=False)  # catatan internal platform, tidak terlihat tenant
    body = models.TextField(max_length=5000)

    class Meta:
        ordering = ["created_at"]
