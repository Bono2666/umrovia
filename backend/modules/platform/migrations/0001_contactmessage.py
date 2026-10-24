import uuid

from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="ContactMessage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=150)),
                ("company", models.CharField(blank=True, max_length=200)),
                ("email", models.EmailField(max_length=254)),
                ("phone", models.CharField(blank=True, max_length=32)),
                ("topic", models.CharField(choices=[("product", "Produk & demo"), ("pricing", "Harga & pembayaran"), ("support", "Bantuan penggunaan"), ("privacy", "Privasi & data pribadi")], max_length=16)),
                ("message", models.TextField(max_length=4000)),
                ("consented_at", models.DateTimeField(default=timezone.now)),
                ("created_at", models.DateTimeField(default=timezone.now)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
