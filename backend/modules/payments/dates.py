from zoneinfo import ZoneInfo

from django.utils import timezone


def tenant_today(tenant):
    return timezone.now().astimezone(ZoneInfo(tenant.timezone)).date()
