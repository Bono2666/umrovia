"""Base model bersama: PK UUID + timestamps (konvensi Spec §5)."""
import uuid

from django.db import models


class UUIDPkMixin(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedMixin(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseAppModel(UUIDPkMixin, TimeStampedMixin):
    """Model dasar umrovia: UUID PK + created_at/updated_at."""

    class Meta:
        abstract = True
