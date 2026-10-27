"""CRM & Lead (PRD MOD-19): prospek dari sumber hingga menjadi jamaah/booking.

Lead tidak billable (PRD §42: "Lead/prospek dibuat → tidak dikenai biaya").
Data tenant: RLS ENABLE+FORCE sejak tabel dibuat (ADR-0003).
"""
import secrets

from django.db import models

from common.models import BaseAppModel
from modules.tenants.managers import TenantScopedModel


class LeadSource(models.TextChoices):
    WALK_IN = "WALK_IN", "Datang ke kantor"
    WHATSAPP = "WHATSAPP", "WhatsApp"
    INSTAGRAM = "INSTAGRAM", "Instagram"
    FACEBOOK = "FACEBOOK", "Facebook"
    TIKTOK = "TIKTOK", "TikTok"
    WEBSITE = "WEBSITE", "Website"
    REFERRAL = "REFERRAL", "Referensi jamaah/kerabat"
    EVENT = "EVENT", "Pameran/kajian"
    OTHER = "OTHER", "Lainnya"


class LeadStage(models.TextChoices):
    NEW = "NEW", "Baru"
    CONTACTED = "CONTACTED", "Sudah dihubungi"
    QUALIFIED = "QUALIFIED", "Berminat serius"
    QUOTED = "QUOTED", "Penawaran dikirim"
    WON = "WON", "Jadi jamaah"
    LOST = "LOST", "Tidak jadi"


OPEN_STAGES = [LeadStage.NEW, LeadStage.CONTACTED, LeadStage.QUALIFIED, LeadStage.QUOTED]


def generate_lead_code() -> str:
    return f"LD-{secrets.token_hex(4).upper()}"


class Lead(TenantScopedModel, BaseAppModel):
    environment = models.CharField(max_length=16)
    code = models.CharField(max_length=16)
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=32, blank=True, default="")  # kanonis +62
    email = models.EmailField(blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    source = models.CharField(max_length=16, choices=LeadSource.choices, default=LeadSource.OTHER)
    interest_package = models.ForeignKey("catalog.TravelPackage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    interest_departure = models.ForeignKey("departures.Departure", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    pax = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True, default="")
    stage = models.CharField(max_length=16, choices=LeadStage.choices, default=LeadStage.NEW)
    stage_changed_at = models.DateTimeField(auto_now_add=True)
    lost_reason = models.CharField(max_length=240, blank=True, default="")
    owner = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    next_follow_up_at = models.DateTimeField(null=True, blank=True)
    converted_pilgrim = models.ForeignKey("pilgrims.Pilgrim", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    converted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey("identity.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "environment", "code"], name="uq_lead_code"),
            models.CheckConstraint(condition=models.Q(pax__gte=1, pax__lte=100), name="ck_lead_pax"),
        ]
        indexes = [
            models.Index(fields=["tenant", "environment", "stage"], name="ix_lead_stage"),
            models.Index(fields=["tenant", "environment", "next_follow_up_at"], name="ix_lead_follow_up"),
            models.Index(fields=["tenant", "phone"], name="ix_lead_phone"),
        ]


class ActivityKind(models.TextChoices):
    NOTE = "NOTE", "Catatan"
    CALL = "CALL", "Telepon"
    WHATSAPP = "WHATSAPP", "WhatsApp"
    MEETING = "MEETING", "Pertemuan"
    STAGE = "STAGE", "Perubahan tahap"
    CONVERTED = "CONVERTED", "Konversi"


class LeadActivity(TenantScopedModel, BaseAppModel):
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="activities")
    kind = models.CharField(max_length=16, choices=ActivityKind.choices)
    body = models.TextField(max_length=2000, blank=True, default="")
    actor = models.ForeignKey("identity.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-created_at"]
