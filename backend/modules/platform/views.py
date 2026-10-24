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
        payload = {
            "status": "ok" if db_ok else "degraded",
            "service": "umrovia-api",
            "version": settings.VERSION,
            "time": timezone.now().isoformat(),
            "checks": {"database": "ok" if db_ok else "error"},
        }
        return Response(payload, status=status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE)
