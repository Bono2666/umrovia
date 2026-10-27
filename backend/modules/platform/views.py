"""Health & readiness endpoint (S01/T04)."""
import logging

from django.conf import settings
from django.db import connection
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.platform.serializers import ContactMessageSerializer
from modules.platform.services import send_contact_notification

logger = logging.getLogger(__name__)


class ContactMessageView(APIView):
    """Store a consented enquiry and notify staff; no public message access."""

    authentication_classes = []
    permission_classes = []
    throttle_scope = "contact-submit"

    @extend_schema(
        request=ContactMessageSerializer,
        responses={201: inline_serializer(name="ContactReference", fields={"reference": drf_serializers.UUIDField()})},
        tags=["Public website"],
    )
    def post(self, request):
        serializer = ContactMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = serializer.save()
        send_contact_notification(message)
        return Response({"reference": str(message.pk)}, status=status.HTTP_201_CREATED)


class HealthView(APIView):
    """GET /api/v1/health/ — public liveness + readiness ringan (DB check)."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        db_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            logger.exception("health: database tidak dapat dihubungi")
            db_ok = False
        checks = {"database": "ok" if db_ok else "error", **readiness_checks(db_ok)}
        payload = {
            "status": "ok" if db_ok and not {"error", "stale", "backlog"} & set(checks.values()) else "degraded",
            "service": "umrovia-api",
            "version": settings.VERSION,
            "time": timezone.now().isoformat(),
            # S19 monitoring: status saja (tanpa angka/data) — aman untuk probe publik.
            "checks": checks,
        }
        # Hanya database yang membuat probe gagal (503); cache/worker/antrean = sinyal alert.
        return Response(payload, status=status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE)


def readiness_checks(db_ok) -> dict:
    """Cache, heartbeat worker dan antrean email macet (> 15 menit lewat jatuh tempo)."""
    import time
    from datetime import timedelta

    from django.core.cache import cache

    from modules.notifications.models import NotificationJob

    result = {}
    try:
        cache.set("health:probe", "1", 30)
        result["cache"] = "ok" if cache.get("health:probe") == "1" else "error"
    except Exception:
        logger.exception("health: cache tidak dapat dihubungi")
        result["cache"] = "error"
    beat = cache.get(WORKER_HEARTBEAT_KEY) if result["cache"] == "ok" else None
    result["worker"] = "unknown" if beat is None else "ok" if time.time() - float(beat) < 120 else "stale"
    if db_ok:
        stuck = NotificationJob.objects.filter(due_at__lt=timezone.now() - timedelta(minutes=15)).exists()
        result["email_queue"] = "backlog" if stuck else "ok"
    return result


WORKER_HEARTBEAT_KEY = "worker:heartbeat"
