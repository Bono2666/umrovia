"""Public website enquiries, separate from tenant operational data."""
import uuid

from django.db import models
from django.utils import timezone


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
