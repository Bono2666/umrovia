"""Trial API — Spec §8.2: /trial/status, /trial/convert, /trial/demo-bookings,
/trial/demo-data. Endpoint platform (`/platform/trials`, extend) → S16."""
import logging

from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.tenants.rbac import require_permission
from modules.trial import services
from modules.trial.models import DemoBooking, TenantTrial

logger = logging.getLogger(__name__)

WALLET_EXPLANATION = (
    "Konversi berhasil. Biaya trial Rp0 — tidak ada tagihan. "
    "Setelah workspace aktif, SaaS wallet top-up dan charge Rp50.000 per "
    "booking-jamaah hanya berlaku pada DP terverifikasi."
)


class ConfirmConvertSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(required=True, help_text="Konfirmasi eksplisit konversi (Owner).")


class DemoBookingSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=200, required=False, allow_blank=True, default="", help_text="Nama paket/jadwal dummy.")


def _require_confirm(validated: dict) -> None:
    if not validated.get("confirm"):
        raise serializers.ValidationError({"confirm": "Konfirmasi wajib diisi `true` untuk konversi trial."})


class TrialStatusView(APIView):
    """GET /trial/status — timer, kuota & status konversi (Role: Owner/Admin §8.2)."""

    permission_classes = [IsAuthenticated, require_permission("trial.read")]

    def get(self, request):
        tenant = request.tenant
        trial = services.get_trial(tenant)
        return Response(services.status_payload(tenant, trial), status=status.HTTP_200_OK)


class TrialConvertView(APIView):
    """POST /trial/convert — konversi dini (Role: Owner §8.2), idempoten (TR09).

    Konversi/expiry TIDAK PERNAH membuat charge berbayar (POL-10) — hanya
    transisi TRIAL → ACTIVE + penutupan demo writes.
    """

    permission_classes = [IsAuthenticated, require_permission("trial.convert")]

    def post(self, request):
        serializer = ConfirmConvertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _require_confirm(serializer.validated_data)

        tenant = request.tenant
        services.get_trial(tenant)  # defensif: tenant lama tanpa trial record
        trial, converted_now = services.convert_trial(tenant, actor=request.user, trigger="manual")
        logger.info(
            "trial convert",
            extra={"tenant": tenant.slug, "trigger": "manual", "converted_now": converted_now},
        )
        payload = services.status_payload(tenant, trial)
        payload.update(
            {
                "converted": True,
                "converted_now": converted_now,
                "tenant_state": tenant.state,
                "message": WALLET_EXPLANATION,
            }
        )
        return Response(payload, status=status.HTTP_200_OK)


class TrialDemoBookingsView(APIView):
    """POST /trial/demo-bookings — booking dummy terkuota (Role: Admin/Sales §8.2)."""

    permission_classes = [IsAuthenticated, require_permission("trial.demo_booking.create")]

    def post(self, request):
        serializer = DemoBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant = request.tenant
        services.get_trial(tenant)
        booking = services.create_demo_booking(
            tenant, actor=request.user, label=serializer.validated_data.get("label", "")
        )
        trial = TenantTrial.objects.get(tenant=tenant)
        return Response(
            {
                "booking": {
                    "id": str(booking.id),
                    "code": booking.code,
                    "label": booking.label,
                    "created_at": booking.created_at.isoformat(),
                },
                "dummy_bookings_used": trial.dummy_count,
                "dummy_bookings_limit": trial.dummy_booking_limit,
            },
            status=status.HTTP_201_CREATED,
        )


class TrialDemoDataView(APIView):
    """GET /trial/demo-data — data demo read-only, tetap terbaca setelah konversi
    (Role: Owner §8.2; §7.2 langkah 3)."""

    permission_classes = [IsAuthenticated, require_permission("trial.demo_data.read")]

    def get(self, request):
        tenant = request.tenant
        trial = services.get_trial(tenant)
        bookings = DemoBooking.objects.filter(tenant=tenant).order_by("-created_at")
        return Response(
            {
                "read_only": trial.converted_at is not None,
                "dummy_bookings_used": trial.dummy_count,
                "dummy_bookings_limit": trial.dummy_booking_limit,
                "results": [
                    {
                        "id": str(b.id),
                        "code": b.code,
                        "label": b.label,
                        "created_at": b.created_at.isoformat(),
                    }
                    for b in bookings
                ],
            },
            status=status.HTTP_200_OK,
        )
