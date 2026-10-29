import csv
import io
from datetime import UTC, datetime, time, timedelta

from django.db import transaction
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.billing.models import SaaSCharge
from modules.billing.services import current_price
from modules.booking.models import BookingParticipant
from modules.platform.access import require_platform
from modules.tenants.environment import resolve_active_environment
from modules.tenants.rbac import require_permission
from modules.wallet import midtrans, services
from modules.wallet.models import Wallet, WalletLedger, WalletTopup
from modules.wallet.serializers import (
    TopupCreateSerializer,
    TopupSettleSerializer,
    TopupSubmitSerializer,
    ledger_payload,
    topup_payload,
)

IDEMPOTENCY = OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)
LEDGER_PARAMS = [OpenApiParameter("from", OpenApiTypes.DATE), OpenApiParameter("to", OpenApiTypes.DATE), OpenApiParameter("kind", str, enum=["TOPUP", "DEBIT", "REFUND"]), OpenApiParameter("page", int)]


class WalletPagination(PageNumberPagination):
    page_size = 50


def wallet_permission(grant):
    class ActiveWalletPermission(require_permission(grant)):
        def has_permission(self, request, view):
            allowed = super().has_permission(request, view)
            if allowed and (request.user.status != "ACTIVE" or not request.user.email_verified_at):
                raise PermissionDenied("Wallet memerlukan akun aktif dengan email terverifikasi.")
            return allowed
    return ActiveWalletPermission


def _page(request, qs, payload):
    paginator = WalletPagination()
    rows = paginator.paginate_queryset(qs, request)
    return paginator.get_paginated_response([payload(row) for row in rows])


def _ledger(request):
    qs = WalletLedger.objects.all()
    if resolve_active_environment(request.tenant) != "production":
        qs = qs.none()
    for field, lookup in [("from", "created_at__gte"), ("to", "created_at__lt")]:
        raw = request.query_params.get(field)
        if raw:
            try:
                value = parse_date(raw)
            except ValueError:
                value = None
            if value is None or value.isoformat() != raw:
                raise ValidationError({field: "Gunakan tanggal YYYY-MM-DD."})
            if field == "to":
                try:
                    value += timedelta(days=1)
                except OverflowError:
                    raise ValidationError({field: "Tanggal di luar rentang yang didukung."}) from None
            qs = qs.filter(**{lookup: datetime.combine(value, time.min, tzinfo=UTC)})
    if request.query_params.get("from") and request.query_params.get("to") and request.query_params["from"] > request.query_params["to"]:
        raise ValidationError({"to": "Tanggal akhir harus sama atau setelah tanggal awal."})
    kind = request.query_params.get("kind")
    if kind:
        if kind not in {"TOPUP", "DEBIT", "REFUND"}:
            raise ValidationError({"kind": "Jenis mutasi tidak dikenal."})
        qs = qs.filter(kind=kind)
    return qs


class WalletView(APIView):
    permission_classes = [IsAuthenticated, wallet_permission("wallet.read")]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Real SaaS wallet only. Demo returns an unfunded preview without creating a wallet. DP funds remain separate.")
    def get(self, request):
        demo = resolve_active_environment(request.tenant) != "production"
        # A stable wallet snapshot avoids a false mismatch while a top-up
        # commits between the balance query and ledger aggregation.
        wallet = Wallet.objects.select_for_update().first() if not demo else None
        balance = wallet.balance_cached_idr if wallet else 0
        credits = services.ledger_total(wallet) if wallet else 0
        reconciliation = wallet.reconciliations.order_by("-created_at").first() if wallet else None
        rate = current_price().unit_price_idr
        topup_open = not demo and request.tenant.state in {"ACTIVE", "RESTRICTED"} and (wallet is None or wallet.status == "ACTIVE")
        methods = {"manual": topup_open and services.manual_instructions() is not None, "midtrans": topup_open and midtrans.configured()}
        pending = SaaSCharge.objects.filter(status="PENDING").aggregate(count=Count("id"), total=Sum("unit_price_idr")) if not demo else {"count": 0, "total": 0}
        return Response({
            "id": str(wallet.pk) if wallet else None, "currency": "IDR", "environment": "demo" if demo else "production",
            "status": wallet.status if wallet else "UNFUNDED", "balance_idr": balance,
            "standard_rate_idr": rate, "estimated_participant_capacity": balance // rate,
            "pending_participant_count": 0 if demo else BookingParticipant.objects.filter(environment="production", saas_charge_state="pending_charge").count(),
            "pending_charge_count": pending["count"], "pending_charge_idr": pending["total"] or 0,
            "posted_charge_count": 0 if demo else SaaSCharge.objects.filter(status="POSTED").count(),
            "tenant_state": request.tenant.state,
            "version": wallet.version if wallet else 0, "ledger_balance_idr": credits,
            "balance_matches_ledger": balance == credits,
            "topup_available": topup_open and any(methods.values()),
            "topup_methods": methods,
            "provider": "manual", "topup_minimum_idr": None,
            "last_reconciliation": {"at": reconciliation.created_at.isoformat(), "consistent": reconciliation.consistent, "variance_idr": reconciliation.variance_idr} if reconciliation else None,
        })


class LedgerView(APIView):
    permission_classes = [IsAuthenticated, wallet_permission("wallet.read")]

    @extend_schema(responses=OpenApiTypes.OBJECT, parameters=LEDGER_PARAMS)
    def get(self, request):
        return _page(request, _ledger(request), ledger_payload)


class LedgerExportView(APIView):
    permission_classes = [IsAuthenticated, wallet_permission("wallet.export")]

    @extend_schema(responses={(200, "text/csv"): OpenApiTypes.BINARY}, parameters=LEDGER_PARAMS[:-1])
    def get(self, request):
        qs = _ledger(request).order_by("sequence")
        if qs.count() > 10_000:
            raise ValidationError({"from": "Batasi periode ekspor hingga maksimal 10.000 mutasi."})
        stream = io.StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["urutan", "tanggal_utc", "jenis", "nominal_idr", "saldo_setelah_idr", "jenis_referensi", "referensi", "keterangan"])
        for row in qs.iterator():
            # Avoid spreadsheet formula interpretation of user-visible strings.
            description = row.description
            if description.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                description = "'" + description
            writer.writerow([row.sequence, row.created_at.isoformat(), row.kind, row.signed_amount_idr, row.balance_after_idr, row.reference_type, str(row.reference_id), description])
        log_event(action="wallet.ledger.exported", request=request, object_type="wallet_ledger", changes={"rows": qs.count()})
        response = HttpResponse("\ufeff" + stream.getvalue(), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="saas-wallet-ledger.csv"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class TopupListView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        grant = "wallet.topup" if self.request.method == "POST" else "wallet.read"
        return [IsAuthenticated(), wallet_permission(grant)()]

    @extend_schema(operation_id="wallet_topups_list", responses=OpenApiTypes.OBJECT, parameters=[OpenApiParameter("page", int)])
    def get(self, request):
        qs = WalletTopup.objects.all()
        if resolve_active_environment(request.tenant) != "production":
            qs = qs.none()
        return _page(request, qs, topup_payload)

    @extend_schema(request=TopupCreateSerializer, responses={201: OpenApiTypes.OBJECT}, parameters=[IDEMPOTENCY])
    def post(self, request):
        serializer = TopupCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        topup = services.create_topup(actor=request.user, key=request.headers.get("Idempotency-Key"), **serializer.validated_data)
        return Response(topup_payload(topup), status=201)


class TopupDetailView(APIView):
    permission_classes = [IsAuthenticated, wallet_permission("wallet.read")]

    @extend_schema(operation_id="wallet_topup_retrieve", responses=OpenApiTypes.OBJECT)
    def get(self, request, topup_id):
        topup = WalletTopup.objects.filter(pk=topup_id).first() if resolve_active_environment(request.tenant) == "production" else None
        if topup is None:
            raise NotFound("Top-up tidak ditemukan.")
        return Response(topup_payload(topup))


class TopupSubmitView(APIView):
    permission_classes = [IsAuthenticated, wallet_permission("wallet.topup")]

    @extend_schema(request=TopupSubmitSerializer, responses=OpenApiTypes.OBJECT, description="Submit transfer evidence. This never credits the wallet. Identical resubmission is idempotent.")
    def post(self, request, topup_id):
        serializer = TopupSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        topup = services.submit_topup(topup_id=topup_id, actor=request.user, **serializer.validated_data)
        return Response(topup_payload(topup))


class TopupRefreshView(APIView):
    permission_classes = [IsAuthenticated, wallet_permission("wallet.read")]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT, description="Re-read a Midtrans top-up from the Midtrans status API and apply it (idempotent). Useful when webhooks cannot reach this server.")
    def post(self, request, topup_id):
        return Response(topup_payload(services.refresh_gateway_topup(topup_id=topup_id)))


class MidtransNotificationView(APIView):
    """Public Midtrans HTTP notification. No session/CSRF; trust comes only from
    re-reading the status API for known orders. Non-2xx makes Midtrans retry."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "midtrans-notify"

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT, auth=[])
    def post(self, request):
        result = services.handle_gateway_notification(request.data)
        return Response({"received": True, "status": result})


class PlatformTopupSettleView(APIView):
    permission_classes = [IsAuthenticated, require_platform("wallet.settle_topup")]  # S18: + MFA segar

    @extend_schema(request=TopupSettleSerializer, responses=OpenApiTypes.OBJECT, description="Platform staff with Django wallet.settle_topup permission only; requester cannot settle their own top-up. Exact bank settlement reference is globally unique. No tenant role grants this authority.")
    @transaction.atomic
    def post(self, request, tenant_id, topup_id):
        services.assert_platform_billing(request.user)
        serializer = TopupSettleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        topup = services.settle_topup(tenant_id=tenant_id, topup_id=topup_id, actor=request.user, **serializer.validated_data)
        return Response(topup_payload(topup))


class PlatformTopupListView(APIView):
    permission_classes = [IsAuthenticated, require_platform("wallet.settle_topup")]  # S18: + MFA segar

    @extend_schema(responses=OpenApiTypes.OBJECT, parameters=[OpenApiParameter("page", int), OpenApiParameter("status", str)], description="Platform billing review queue for one explicitly scoped tenant; includes transfer evidence references, no pilgrim data.")
    def get(self, request, tenant_id):
        services.assert_platform_billing(request.user)
        with services.platform_tenant_context(tenant_id) as tenant:
            qs = WalletTopup.objects.all()
            status = request.query_params.get("status")
            if status:
                if status not in {"CREATED", "PENDING", "PAID", "EXPIRED", "REJECTED"}:
                    raise ValidationError({"status": "Status tidak dikenal."})
                qs = qs.filter(status=status)
            log_event(action="wallet.topup.platform_reviewed", tenant=tenant, actor=request.user, object_type="wallet_topup")
            return _page(request, qs, topup_payload)
