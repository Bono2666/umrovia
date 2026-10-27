"""API konsol platform `/api/v1/platform/*` (S18) dan tiket dukungan tenant `/api/v1/support/*`."""
from django.db import transaction
from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.models import AuditEvent
from modules.audit.services import log_event
from modules.platform import console, mfa, support
from modules.platform.access import MFA_SESSION_KEY, PlatformStaff, granted, mark_mfa, mfa_fresh, require_platform
from modules.platform.models import StaffMFA, SupportTicket
from modules.tenants.models import Tenant, TenantState


class Pagination(PageNumberPagination):
    page_size = 25


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=240, allow_blank=True)


class DecisionSerializer(ReasonSerializer):
    decision = serializers.ChoiceField(choices=["approve", "reject"])


class ExtendSerializer(ReasonSerializer):
    days = serializers.IntegerField(min_value=1, max_value=30)


class PriceSerializer(ReasonSerializer):
    code = serializers.RegexField(r"^[A-Z0-9][A-Z0-9_-]{2,31}$")
    unit_price_idr = serializers.IntegerField(min_value=1, max_value=10_000_000)
    effective_from = serializers.DateTimeField()


class CodeSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    recovery_code = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")


class TicketSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=160)
    category = serializers.ChoiceField(choices=SupportTicket.Category.choices)
    body = serializers.CharField(max_length=5000)


class MessageSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=5000)
    internal = serializers.BooleanField(required=False, default=False)


class TicketUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=SupportTicket.Status.choices, required=False)
    priority = serializers.ChoiceField(choices=["NORMAL", "HIGH"], required=False)
    assign_to_me = serializers.BooleanField(required=False)


# --------------------------------------------------------------------- MFA --


def _session(request) -> dict:
    device = StaffMFA.objects.filter(user=request.user).first()
    return {
        "email": request.user.email, "full_name": request.user.full_name, "permissions": granted(request.user),
        "mfa": {"enrolled": bool(device and device.confirmed_at), "verified": mfa_fresh(request),
                "recovery_codes_left": len(device.recovery_hashes) if device and device.confirmed_at else 0},
    }


class PlatformMeView(APIView):
    permission_classes = [IsAuthenticated, PlatformStaff]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Platform staff session: granted platform permissions and MFA state.")
    def get(self, request):
        return Response(_session(request))


class MFASetupView(APIView):
    permission_classes = [IsAuthenticated, PlatformStaff]
    throttle_scope = "platform-mfa"

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT, description="Start TOTP enrollment (password re-entry). Returns the secret once; an active device must be reset by another admin.")
    def post(self, request):
        # Kegagalan dicatat di luar blok atomik agar audit tidak ikut ter-rollback.
        if not request.user.check_password(str(request.data.get("password", ""))):
            log_event(action="platform.mfa.setup_denied", actor=request.user, object_type="user", object_id=request.user.pk)
            raise ValidationError({"password": "Password salah."})
        if StaffMFA.objects.filter(user=request.user, confirmed_at__isnull=False).exists():
            raise ValidationError({"mfa": "MFA sudah aktif. Minta admin platform lain untuk mereset bila perangkat hilang."})
        _, secret = mfa.start_enrollment(request.user)
        return Response({"secret": secret, "otpauth_uri": mfa.provisioning_uri(secret, request.user.email)})


class MFAConfirmView(APIView):
    permission_classes = [IsAuthenticated, PlatformStaff]
    throttle_scope = "platform-mfa"

    @extend_schema(request=CodeSerializer, responses=OpenApiTypes.OBJECT, description="Confirm enrollment with a TOTP code; returns 10 single-use recovery codes once.")
    @transaction.atomic
    def post(self, request):
        device = StaffMFA.objects.select_for_update().filter(user=request.user, confirmed_at__isnull=True).first()
        if device is None:
            raise ValidationError({"code": "Mulai pendaftaran MFA terlebih dahulu."})
        codes = mfa.confirm(device, str(request.data.get("code", "")))
        if codes is None:
            raise ValidationError({"code": "Kode tidak cocok. Periksa jam perangkat dan coba lagi."})
        mark_mfa(request)
        log_event(action="platform.mfa.enrolled", actor=request.user, object_type="user", object_id=request.user.pk)
        return Response({**_session(request), "recovery_codes": codes})


class MFAVerifyView(APIView):
    permission_classes = [IsAuthenticated, PlatformStaff]
    throttle_scope = "platform-mfa"

    @extend_schema(request=CodeSerializer, responses=OpenApiTypes.OBJECT, description="Step-up: verify a TOTP code (no reuse) or a single-use recovery code for this session.")
    def post(self, request):
        serializer = CodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recovery = serializer.validated_data["recovery_code"]
        with transaction.atomic():
            device = StaffMFA.objects.select_for_update().filter(user=request.user, confirmed_at__isnull=False).first()
            if device is None:
                raise ValidationError({"mfa": "MFA belum didaftarkan."})
            ok = mfa.use_recovery_code(device, recovery) if recovery else mfa.verify_totp(device, serializer.validated_data["code"])
        if not ok:  # dicatat di luar blok atomik agar percobaan gagal tetap teraudit
            log_event(action="platform.mfa.failed", actor=request.user, object_type="user", object_id=request.user.pk, changes={"type": "recovery" if recovery else "totp"})
            raise ValidationError({"code": "Kode tidak valid atau sudah dipakai."})
        mark_mfa(request)
        log_event(action="platform.mfa.verified", actor=request.user, object_type="user", object_id=request.user.pk, changes={"type": "recovery" if recovery else "totp"})
        return Response(_session(request))

    def delete(self, request):
        request.session.pop(MFA_SESSION_KEY, None)
        return Response(status=204)


# ----------------------------------------------------------------- console --


class OverviewView(APIView):
    permission_classes = [IsAuthenticated, require_platform("platform.console_view")]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Platform aggregates: tenants by state, trials ending, wallet liability, SaaS revenue this month (posted − approved refunds), queues.")
    def get(self, request):
        return Response(console.overview())


class TenantListView(APIView):
    permission_classes = [IsAuthenticated, require_platform("platform.console_view")]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Tenant metadata and usage counts. No pilgrim data; owner email masked.")
    def get(self, request):
        qs = Tenant.objects.prefetch_related("environments").order_by("display_name")
        state = request.query_params.get("state")
        if state:
            if state not in TenantState.values:
                raise ValidationError({"state": "Status tidak dikenal."})
            qs = qs.filter(state=state)
        q = (request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(display_name__icontains=q) | Q(legal_name__icontains=q) | Q(slug__icontains=q))
        paginator = Pagination()
        rows = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response([console.tenant_row(t) for t in rows])


class TenantDetailView(APIView):
    permission_classes = [IsAuthenticated, require_platform("platform.console_view")]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Tenant metadata, masked members, lifecycle requests and platform history. Viewing is audited.")
    def get(self, request, tenant_id):
        return Response(console.tenant_detail(tenant_id, request.user))


class TenantActionView(APIView):
    permission_classes = [IsAuthenticated, require_platform("platform.tenant_manage")]
    action = ""

    @extend_schema(request=ReasonSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, tenant_id):
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data["reason"]
        if self.action == "termination":
            result = console.lifecycle_payload(console.request_termination(tenant_id, actor=request.user, reason=reason))
            return Response(result, status=201)
        getattr(console, self.action)(tenant_id, actor=request.user, reason=reason)
        return Response(console.tenant_row(Tenant.objects.get(pk=tenant_id)))


class TerminationDecisionView(APIView):
    permission_classes = [IsAuthenticated, require_platform("platform.tenant_manage")]

    @extend_schema(request=DecisionSerializer, responses=OpenApiTypes.OBJECT, description="Second platform admin approves or rejects a termination (requester cannot decide).")
    def post(self, request, tenant_id, request_id):
        serializer = DecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = console.decide_termination(tenant_id, request_id, actor=request.user, **serializer.validated_data)
        return Response(console.lifecycle_payload(result))


class TrialListView(APIView):
    permission_classes = [IsAuthenticated, require_platform("platform.console_view")]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response({"results": console.trial_rows(request.query_params.get("status", ""))})


class TrialExtendView(APIView):
    permission_classes = [IsAuthenticated, require_platform("platform.tenant_manage")]

    @extend_schema(request=ExtendSerializer, responses=OpenApiTypes.OBJECT, description="Reasoned, audited trial extension (1–30 days).")
    def post(self, request, tenant_id):
        serializer = ExtendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trial = console.extend_trial(tenant_id, actor=request.user, **serializer.validated_data)
        return Response(console._trial_payload(trial))


class PricingView(APIView):
    def get_permissions(self):
        grant = "platform.pricing_manage" if self.request.method == "POST" else "platform.console_view"
        return [IsAuthenticated(), require_platform(grant)()]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response({"results": console.price_rows()})

    @extend_schema(request=PriceSerializer, responses=OpenApiTypes.OBJECT, description="Publish a future price version (≥1 hour ahead). Existing versions and posted charges are never changed.")
    def post(self, request):
        serializer = PriceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        console.publish_price(actor=request.user, **serializer.validated_data)
        return Response({"results": console.price_rows()}, status=201)


class AuditView(APIView):
    permission_classes = [IsAuthenticated, require_platform("platform.audit_view")]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Platform-wide audit trail with masked actors and allow-listed change keys only.")
    def get(self, request):
        qs = AuditEvent.objects.select_related("tenant", "actor").order_by("-occurred_at")
        params = request.query_params
        if params.get("tenant"):
            qs = qs.filter(tenant__slug=params["tenant"])
        if params.get("action"):
            qs = qs.filter(action__startswith=params["action"])
        if params.get("platform") == "1":
            qs = qs.filter(Q(action__startswith="platform.") | Q(actor__is_staff=True))
        paginator = Pagination()
        rows = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(console.audit_rows(rows))


class BillingQueueView(APIView):
    permission_classes = [IsAuthenticated, require_platform("platform.console_view")]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Cross-tenant top-ups awaiting settlement and refunds awaiting decision (billing permissions required to act).")
    def get(self, request):
        if not (request.user.has_perm("wallet.settle_topup") or request.user.has_perm("billing.approve_adjustment")):
            raise PermissionDenied("Antrean billing hanya untuk petugas billing platform.")
        return Response(console.billing_queue())


# ----------------------------------------------------------------- support --


def _ticket(ticket_id, **filters):
    ticket = SupportTicket.objects.select_related("tenant", "opened_by", "assigned_to").filter(pk=ticket_id, **filters).first()
    if ticket is None:
        raise NotFound("Tiket tidak ditemukan.")
    return ticket


class PlatformTicketListView(APIView):
    permission_classes = [IsAuthenticated, require_platform("platform.support_manage")]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        qs = SupportTicket.objects.select_related("tenant", "opened_by", "assigned_to")
        status = request.query_params.get("status")
        if status == "active":
            qs = qs.exclude(status=SupportTicket.Status.RESOLVED)
        elif status:
            if status not in SupportTicket.Status.values:
                raise ValidationError({"status": "Status tidak dikenal."})
            qs = qs.filter(status=status)
        if request.query_params.get("tenant"):
            qs = qs.filter(tenant__slug=request.query_params["tenant"])
        paginator = Pagination()
        rows = paginator.paginate_queryset(qs.order_by("-last_message_at"), request)
        return paginator.get_paginated_response([support.ticket_payload(t, platform=True) for t in rows])


class PlatformTicketDetailView(APIView):
    permission_classes = [IsAuthenticated, require_platform("platform.support_manage")]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Ticket thread incl. internal notes and diagnosis metadata (counts only, no pilgrim data).")
    def get(self, request, ticket_id):
        ticket = _ticket(ticket_id)
        data = support.ticket_payload(ticket, platform=True, messages=True)
        data["diagnosis"] = console.tenant_row(ticket.tenant)
        return Response(data)

    @extend_schema(request=TicketUpdateSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request, ticket_id):
        serializer = TicketUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = support.update_ticket(_ticket(ticket_id), user=request.user, **serializer.validated_data)
        return Response(support.ticket_payload(ticket, platform=True, messages=True))


class PlatformTicketMessageView(APIView):
    permission_classes = [IsAuthenticated, require_platform("platform.support_manage")]

    @extend_schema(request=MessageSerializer, responses=OpenApiTypes.OBJECT, description="Reply to the tenant (emails the opener) or add an internal note.")
    def post(self, request, ticket_id):
        serializer = MessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = support.platform_reply(_ticket(ticket_id), user=request.user, **serializer.validated_data)
        return Response(support.ticket_payload(ticket, platform=True, messages=True), status=201)


class TenantMember(BasePermission):
    """Semua anggota aktif travel boleh membuka tiket untuk travel-nya."""

    def has_permission(self, request, view):
        if getattr(request, "membership", None) is None:
            raise PermissionDenied("Pilih workspace travel terlebih dahulu.")
        return True


class SupportTicketListView(APIView):
    permission_classes = [IsAuthenticated, TenantMember]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        paginator = Pagination()
        rows = paginator.paginate_queryset(SupportTicket.objects.filter(tenant=request.tenant).select_related("opened_by").order_by("-last_message_at"), request)
        return paginator.get_paginated_response([support.ticket_payload(t) for t in rows])

    @extend_schema(request=TicketSerializer, responses=OpenApiTypes.OBJECT, description="Open a ticket for the active workspace. Do not include ID/passport numbers.")
    def post(self, request):
        serializer = TicketSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = support.open_ticket(tenant=request.tenant, user=request.user, **serializer.validated_data)
        return Response(support.ticket_payload(ticket, messages=True), status=201)


class SupportTicketDetailView(APIView):
    permission_classes = [IsAuthenticated, TenantMember]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, ticket_id):
        return Response(support.ticket_payload(_ticket(ticket_id, tenant=request.tenant), messages=True))


class SupportTicketMessageView(APIView):
    permission_classes = [IsAuthenticated, TenantMember]

    @extend_schema(request=MessageSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, ticket_id):
        ticket = support.tenant_reply(_ticket(ticket_id, tenant=request.tenant), user=request.user, body=request.data.get("body", ""))
        return Response(support.ticket_payload(ticket, messages=True), status=201)


class SupportTicketResolveView(APIView):
    permission_classes = [IsAuthenticated, TenantMember]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT, description="Tenant marks its ticket as resolved; replying reopens it.")
    def post(self, request, ticket_id):
        ticket = _ticket(ticket_id, tenant=request.tenant)
        ticket = support.update_ticket(ticket, user=request.user, status=SupportTicket.Status.RESOLVED)
        return Response(support.ticket_payload(ticket, messages=True))
