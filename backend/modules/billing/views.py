from django.db import transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.billing import services
from modules.billing.models import SaaSAdjustment, SaaSCharge
from modules.billing.services import charge_status
from modules.platform.access import require_platform
from modules.tenants.environment import resolve_active_environment
from modules.wallet.serializers import StrictSerializer
from modules.wallet.views import _page, wallet_permission

STATUSES = {"PENDING", "POSTED", "VOID", "REFUNDED"}


class RefundRequestSerializer(StrictSerializer):
    reason = serializers.CharField(max_length=2000)


class RefundDecisionSerializer(StrictSerializer):
    decision = serializers.ChoiceField(choices=["APPROVED", "REJECTED"])
    reason = serializers.CharField(max_length=2000)


def adjustment_payload(row):
    return {
        "id": str(row.pk), "charge_id": str(row.charge_id), "amount_idr": row.amount_idr, "status": row.status,
        "reason": row.reason, "decision_reason": row.decision_reason, "created_at": row.created_at.isoformat(),
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "ledger_entry_id": str(row.ledger_entry_id) if row.ledger_entry_id else None,
    }


def charge_payload(row, *, pii=True):
    participant = row.participant
    adjustment = next((a for a in row.adjustments.all() if a.status != "REJECTED"), None)
    payload = {
        "id": str(row.pk), "status": row.status, "saas_charge_status": charge_status(row), "pending_reason": row.pending_reason,
        "unit_price_idr": row.unit_price_idr, "price_version": row.price_version.code,
        "booking_id": str(row.booking_id), "booking_code": row.booking.code,
        "booking_participant_id": str(participant.pk), "booking_passenger_id": str(participant.booking_passenger_id),
        "participant_status": participant.participant_status, "eligible_at": row.eligible_at.isoformat(),
        "charged_at": row.charged_at.isoformat() if row.charged_at else None, "attempts": row.attempts,
        "ledger_entry_id": str(row.ledger_entry_id) if row.ledger_entry_id else None, "void_reason": row.void_reason,
        "refund": adjustment_payload(adjustment) if adjustment else None,
        "refundable": row.status == "POSTED" and participant.participant_status == "CANCELED" and adjustment is None,
    }
    if pii:
        payload["pilgrim_name"] = participant.pilgrim.name
    return payload


def _charges(request):
    qs = SaaSCharge.objects.select_related("participant__pilgrim", "booking", "price_version").prefetch_related("adjustments")
    if resolve_active_environment(request.tenant) != "production":
        return qs.none()
    status = request.query_params.get("status")
    if status:
        if status not in STATUSES:
            raise ValidationError({"status": "Status charge tidak dikenal."})
        qs = qs.filter(status=status)
    return qs.order_by("-eligible_at", "-id")


class ChargeListView(APIView):
    permission_classes = [IsAuthenticated, wallet_permission("wallet.read")]

    @extend_schema(operation_id="wallet_charges_list", responses=OpenApiTypes.OBJECT, parameters=[OpenApiParameter("status", str, enum=sorted(STATUSES)), OpenApiParameter("page", int)], description="SaaS charges per booking-participant with pending reason and refund state. Demo returns none.")
    def get(self, request):
        return _page(request, _charges(request), charge_payload)


class ChargeRetryView(APIView):
    permission_classes = [IsAuthenticated, wallet_permission("wallet.topup")]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT, description="Retry pending charges FIFO with the current wallet balance. Idempotent: posted charges are never debited twice.")
    def post(self, request):
        result = services.retry_pending_charges(actor=request.user)
        log_event(action="saas.charge.retry_requested", request=request, object_type="wallet", changes=result)
        return Response(result)


class RefundRequestView(APIView):
    permission_classes = [IsAuthenticated, wallet_permission("wallet.refund_request")]

    @extend_schema(request=RefundRequestSerializer, responses={201: OpenApiTypes.OBJECT}, description="Request platform review of a posted charge for a canceled participant. No wallet credit until platform approval; identical retry returns the same request.")
    def post(self, request, charge_id):
        serializer = RefundRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        adjustment = services.request_refund(charge_id=charge_id, actor=request.user, **serializer.validated_data)
        return Response(adjustment_payload(adjustment), status=201)


class PlatformRefundListView(APIView):
    permission_classes = [IsAuthenticated, require_platform("billing.approve_adjustment")]  # S18: + MFA segar

    @extend_schema(responses=OpenApiTypes.OBJECT, parameters=[OpenApiParameter("status", str, enum=["REQUESTED", "APPROVED", "REJECTED"]), OpenApiParameter("page", int)], description="Platform billing queue for one explicit tenant; booking references only, no pilgrim data.")
    def get(self, request, tenant_id):
        services.assert_platform_refund(request.user)
        with services.platform_tenant_context(tenant_id) as tenant:
            qs = SaaSAdjustment.objects.select_related("charge__booking", "charge__participant", "charge__price_version")
            status = request.query_params.get("status")
            if status:
                if status not in {"REQUESTED", "APPROVED", "REJECTED"}:
                    raise ValidationError({"status": "Status tidak dikenal."})
                qs = qs.filter(status=status)
            log_event(action="saas.refund.platform_reviewed", tenant=tenant, actor=request.user, object_type="saas_adjustment")
            return _page(request, qs, lambda row: {**adjustment_payload(row), "booking_code": row.charge.booking.code, "booking_passenger_id": str(row.charge.participant.booking_passenger_id), "participant_status": row.charge.participant.participant_status})


class PlatformRefundDecisionView(APIView):
    permission_classes = [IsAuthenticated, require_platform("billing.approve_adjustment")]  # S18: + MFA segar

    @extend_schema(request=RefundDecisionSerializer, responses=OpenApiTypes.OBJECT, description="Platform staff with Django billing.approve_adjustment only. APPROVED appends one compensating REFUND ledger credit; replay returns the same decision.")
    @transaction.atomic
    def post(self, request, tenant_id, adjustment_id):
        services.assert_platform_refund(request.user)
        serializer = RefundDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        adjustment = services.decide_refund(tenant_id=tenant_id, adjustment_id=adjustment_id, actor=request.user, **serializer.validated_data)
        return Response(adjustment_payload(adjustment))
