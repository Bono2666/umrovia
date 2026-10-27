import hashlib
from uuid import UUID

from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.api import list_response
from modules.audit.services import log_event
from modules.billing.services import charge_preview, lock_wallet
from modules.booking.models import Booking, BookingParticipant
from modules.booking.serializers import booking_payload
from modules.payments import services
from modules.payments.models import PaymentAllocation, TravelInvoice, TravelPayment, TravelReceipt
from modules.payments.policy import payment_rules, validate_payment_rules
from modules.payments.serializers import (
    IssueInvoiceSerializer,
    PaymentActionSerializer,
    PaymentCreateSerializer,
    PaymentEvidenceSerializer,
    PaymentRulesSerializer,
    invoice_payload,
    payment_payload,
)
from modules.tenants.environment import assert_environment_writable, resolve_active_environment
from modules.tenants.models import TenantSettings
from modules.tenants.rbac import has_permission, permission_list, require_permission
from modules.travel_finance.models import TravelBankAccount


def _get(queryset, **lookup):
    obj = queryset.filter(**lookup).first()
    if obj is None:
        raise NotFound("Data tidak ditemukan.")
    return obj


def _payments(request):
    # S19 (uji beban): tanpa N+1 dan tanpa memuat PDF di daftar.
    qs = (
        TravelPayment.objects.select_related("booking", "invoice", "verified_by", "receipt")
        .defer("invoice__pdf_data", "invoice__snapshot_json", "receipt__pdf_data", "receipt__snapshot_json")
        .prefetch_related(
            Prefetch("allocations", queryset=PaymentAllocation.objects.select_related("participant__pilgrim")),
            Prefetch("booking__participants", queryset=BookingParticipant.objects.prefetch_related("saas_charges")),
        )
    )
    if not has_permission(permission_list(request.membership.role), "payments.read_all"):
        qs = qs.filter(created_by=request.user)
    return qs


def _filter_uuid(value, field):
    try:
        return UUID(str(value))
    except ValueError:
        raise ValidationError({field: "ID tidak valid."}) from None


class InvoiceListView(APIView):
    permission_classes = [IsAuthenticated, require_permission("invoices.read")]

    @extend_schema(operation_id="invoices_list", responses=OpenApiTypes.OBJECT, parameters=[OpenApiParameter("booking", OpenApiTypes.UUID), OpenApiParameter("status", str)])
    def get(self, request):
        qs = TravelInvoice.objects.select_related("booking", "tenant").defer("pdf_data")  # S19: tanpa N+1/PDF
        if request.query_params.get("booking"):
            qs = qs.filter(booking_id=_filter_uuid(request.query_params["booking"], "booking"))
        if request.query_params.get("status"):
            if request.query_params["status"] not in {"ISSUED", "PARTIALLY_PAID", "PAID", "VOIDED"}:
                raise ValidationError({"status": "Status invoice tidak dikenal."})
            qs = qs.filter(status=request.query_params["status"])
        if request.query_params.get("open") == "1":  # pilihan invoice untuk mencatat pembayaran
            qs = qs.filter(status__in=["ISSUED", "PARTIALLY_PAID"])
        search = (request.query_params.get("q") or "").strip()
        if search:  # S19: cari invoice saat jumlahnya melebihi satu halaman pilihan
            qs = qs.filter(Q(invoice_number__icontains=search) | Q(booking__code__icontains=search) | Q(snapshot_json__buyer_name__icontains=search))
        return list_response(request, qs.order_by("-issue_at", "invoice_number"), invoice_payload)


class InvoiceCandidatesView(APIView):
    permission_classes = [IsAuthenticated, require_permission("invoices.issue")]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        environment = resolve_active_environment(request.tenant)
        qs = Booking.objects.filter(environment=environment).exclude(status__in=["DRAFT", "CANCELED", "EXPIRED"]).filter(invoice__isnull=True)
        qs = qs.select_related("departure__package", "created_by", "canceled_by").prefetch_related("participants__pilgrim", "price_lines")
        return Response({"results": [booking_payload(row) for row in qs[:200]]})


class InvoiceDetailView(APIView):
    permission_classes = [IsAuthenticated, require_permission("invoices.read")]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, invoice_id):
        return Response(invoice_payload(_get(TravelInvoice.objects.select_related("booking"), pk=invoice_id)))


class IssueInvoiceView(APIView):
    permission_classes = [IsAuthenticated, require_permission("invoices.issue")]

    @extend_schema(request=IssueInvoiceSerializer, responses=OpenApiTypes.OBJECT, description="Issue invoice idempotently from frozen participant pricing. Optional DP target never blocks payment eligibility.")
    @transaction.atomic
    def post(self, request, booking_id):
        booking = _get(Booking.objects, pk=booking_id)
        serializer = IssueInvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = services.issue_invoice(booking_id=booking.pk, actor=request.user, **serializer.validated_data)
        return Response(invoice_payload(invoice))


class PaymentListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        return [IsAuthenticated(), require_permission("payments.create" if self.request.method == "POST" else "payments.read")()]

    @extend_schema(operation_id="payments_list", responses=OpenApiTypes.OBJECT, parameters=[OpenApiParameter("invoice", OpenApiTypes.UUID), OpenApiParameter("status", str)])
    def get(self, request):
        qs = _payments(request)
        if request.query_params.get("invoice"):
            qs = qs.filter(invoice_id=_filter_uuid(request.query_params["invoice"], "invoice"))
        if request.query_params.get("status"):
            if request.query_params["status"] not in {"DRAFT", "SUBMITTED", "VERIFIED", "REJECTED", "REVERSED"}:
                raise ValidationError({"status": "Status pembayaran tidak dikenal."})
            qs = qs.filter(status=request.query_params["status"])
        return list_response(request, qs.order_by("-received_at", "id"), payment_payload)

    @extend_schema(request=PaymentCreateSerializer, responses={201: OpenApiTypes.OBJECT}, parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)])
    @transaction.atomic
    def post(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        invoice = data["invoice"]
        booking = _get(Booking.objects.select_for_update(), pk=invoice.booking_id)
        assert_environment_writable(request.tenant, booking.environment)
        result = services.idempotent_operation(
            request=request, action="record", booking=booking, target=invoice.pk,
            factory=lambda: payment_payload(services.record_payment(invoice_id=invoice.pk, actor=request.user, data=data)),
        )
        return Response(result, status=201)


class PaymentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        return [IsAuthenticated(), require_permission("payments.create" if self.request.method == "PATCH" else "payments.read")()]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, payment_id):
        return Response(payment_payload(_get(_payments(request), pk=payment_id)))

    @extend_schema(request=PaymentEvidenceSerializer, responses=OpenApiTypes.OBJECT)
    @transaction.atomic
    def patch(self, request, payment_id):
        initial = _get(_payments(request), pk=payment_id)
        booking = _get(Booking.objects.select_for_update(), pk=initial.booking_id)
        payment = _get(TravelPayment.objects.select_for_update(), pk=payment_id)
        services.assert_booking_payable(booking)
        if payment.status != "DRAFT":
            raise ValidationError({"status": "Bukti hanya dapat dilengkapi selama DRAFT."})
        serializer = PaymentEvidenceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data:
            raise ValidationError({"evidence_ref": "Isi bukti atau referensi penerimaan."})
        for field, value in serializer.validated_data.items():
            setattr(payment, field, value)
        from django.db import IntegrityError

        try:
            with transaction.atomic():
                payment.save(update_fields=[*serializer.validated_data, "updated_at"])
        except IntegrityError:
            raise services.Conflict("Referensi pembayaran sudah pernah dicatat.") from None
        log_event(action="payments.evidence.updated", request=request, object_type="payment", object_id=payment.pk)
        return Response(payment_payload(payment))


class PaymentActionView(APIView):
    permission_classes = [IsAuthenticated]
    action = "verify"

    def get_permissions(self):
        grant = "payments.create" if self.action == "submit" else "payments.reverse" if self.action == "reverse" else "payments.verify"
        return [IsAuthenticated(), require_permission(grant)()]

    @extend_schema(request=PaymentActionSerializer, responses=OpenApiTypes.OBJECT, parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)], description="Payment state transition. Verification persists DP, issues one receipt and attempts one SaaS charge per eligible production participant; insufficient wallet still returns 200 with saas_charge_status PENDING_INSUFFICIENT_FUNDS. Reversal requires a different approver and a reason and never refunds a posted charge.")
    @transaction.atomic
    def post(self, request, payment_id):
        # Cakupan Sales hanya pembayarannya sendiri, Finance/Owner read_all.
        initial = _get(_payments(request), pk=payment_id)
        if self.action == "verify" and initial.environment == "production":
            lock_wallet(request.tenant)  # urutan lock S13: wallet sebelum booking
        booking = _get(Booking.objects.select_for_update(), pk=initial.booking_id)
        payment = _get(TravelPayment.objects.select_for_update(), pk=payment_id)
        assert_environment_writable(request.tenant, payment.environment)
        serializer = PaymentActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "allocations" in data:
            expected = sorted((str(row.participant_id), row.amount_idr) for row in payment.allocations.all())
            supplied = sorted((str(row["booking_participant_id"]), row["amount_idr"]) for row in data["allocations"])
            if supplied != expected:
                raise ValidationError({"allocations": "Alokasi harus cocok dengan pembayaran yang diajukan."})
        if "verified_received_at" in data and data["verified_received_at"] != payment.received_at:
            raise ValidationError({"verified_received_at": "Tanggal harus cocok dengan pembayaran yang diajukan."})
        if "evidence_ref" in data and data["evidence_ref"] != payment.evidence_ref:
            raise ValidationError({"evidence_ref": "Bukti harus cocok dengan pembayaran yang diajukan."})

        def execute():
            if self.action == "submit":
                services.assert_booking_payable(booking)
                result = services.submit_payment(payment=payment, actor=request.user)
            elif self.action == "verify":
                result = services.verify_payment(payment_id=payment_id, actor=request.user, note=data.get("verification_note", ""))
            elif self.action == "reverse":
                result = services.reverse_payment(payment_id=payment_id, actor=request.user, reason=data.get("reason", ""))
            else:
                result = services.reject_payment(payment_id=payment_id, actor=request.user, reason=data.get("reason", ""))
            return payment_payload(result)

        return Response(services.idempotent_operation(request=request, action=self.action, booking=booking, target=payment.pk, factory=execute))


class PaymentChargePreviewView(APIView):
    permission_classes = [IsAuthenticated, require_permission("payments.verify")]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="SaaS charge preview before DP verification: eligible participants, effective fee, already-charged flags. Wallet balance only for roles with wallet.read.")
    def get(self, request, payment_id):
        payment = _get(_payments(request), pk=payment_id)
        show_wallet = has_permission(permission_list(request.membership.role), "wallet.read")
        return Response(charge_preview(payment, show_wallet=show_wallet))


class PaymentOptionsView(APIView):
    permission_classes = [IsAuthenticated, require_permission("payments.create")]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response({"bank_accounts": list(TravelBankAccount.objects.filter(active=True).values("id", "bank_name", "account_name", "account_masked"))})


class PaymentSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        return [IsAuthenticated(), require_permission("tenant.settings.write" if self.request.method == "PATCH" else "invoices.read")()]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(payment_rules(request.tenant))

    @extend_schema(request=PaymentRulesSerializer, responses=OpenApiTypes.OBJECT, description="Optional dp_minimum_idr target; eligibility always uses verified allocations > 0. maker_checker requires a different verifier when enabled.")
    @transaction.atomic
    def patch(self, request):
        if not isinstance(request.data, dict):
            raise ValidationError({"payments": "Aturan pembayaran harus berupa objek."})
        serializer = PaymentRulesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        policy = validate_payment_rules({**payment_rules(request.tenant), **serializer.validated_data})
        policy["dp_policy"] = "any_positive"
        settings, _ = TenantSettings.objects.get_or_create(tenant=request.tenant)
        settings = TenantSettings.objects.select_for_update().get(pk=settings.pk)
        settings.rules_json = {**settings.rules_json, "payments": policy}
        settings.save(update_fields=["rules_json", "updated_at"])
        log_event(action="payments.settings.updated", request=request, object_type="tenant_settings", object_id=request.tenant.pk, changes=policy)
        return Response(policy)


class InvoicePdfView(APIView):
    permission_classes = [IsAuthenticated, require_permission("invoices.read")]

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, invoice_id):
        return _pdf_response(request, _get(TravelInvoice.objects, pk=invoice_id), "invoice_number")


class ReceiptPdfView(APIView):
    permission_classes = [IsAuthenticated, require_permission("receipts.read")]

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, receipt_id):
        receipt = _get(TravelReceipt.objects, pk=receipt_id)
        _get(_payments(request), pk=receipt.payment_id)
        return _pdf_response(request, receipt, "receipt_no")


def _pdf_response(request, document, number_field):
    data = bytes(document.pdf_data)
    if hashlib.sha256(data).hexdigest() != document.checksum:
        raise ValidationError({"document": "Checksum dokumen tidak cocok."})
    log_event(action="financial_document.downloaded", request=request, object_type=document._meta.label_lower, object_id=document.pk)
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{getattr(document, number_field)}.pdf"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
