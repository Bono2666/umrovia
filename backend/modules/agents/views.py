"""API Agen & Komisi (MOD-10): /agents, /commission-policies, /commissions, /bookings/{id}/agent.

Grant: `agents.read`/`agents.manage` (master agen), `commissions.read`,
`commissions.policies` (kebijakan), `commissions.approve`, `commissions.pay`.
Owner memakai wildcard. Agen booking diubah dengan `bookings.create`.
"""
from uuid import UUID

from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.api import list_response
from modules.agents import services
from modules.agents.models import (
    Agent,
    BookingAgentChange,
    Commission,
    CommissionKind,
    CommissionPolicy,
    CommissionStatus,
    CommissionTrigger,
)
from modules.audit.services import log_event
from modules.booking.models import Booking
from modules.catalog.models import TravelPackage
from modules.payments.dates import tenant_today
from modules.tenants.branches import scope_filter
from modules.tenants.environment import assert_environment_writable, resolve_active_environment
from modules.tenants.rbac import require_permission
from modules.travel_finance.models import TravelBankAccount, mask_account_number


def _name(user):
    return (user.full_name or user.email) if user else None


def _uuid(value, field):
    try:
        return UUID(str(value))
    except ValueError:
        raise ValidationError({field: "ID tidak valid."}) from None


def agent_ref(agent):
    return {"id": str(agent.pk), "code": agent.code, "name": agent.name} if agent else None


def agent_payload(agent, stats=None):
    data = {
        "id": str(agent.pk), "code": agent.code, "name": agent.name, "phone": agent.phone, "email": agent.email,
        "business_id": agent.business_id, "bank_name": agent.bank_name, "bank_account_name": agent.bank_account_name,
        "bank_account_masked": agent.bank_account_masked, "area": agent.area, "level": agent.level,
        "active": agent.active, "notes": agent.notes, "created_at": agent.created_at.isoformat(),
    }
    if stats is not None:
        data.update(stats)
    return data


def policy_payload(policy):
    return {
        "id": str(policy.pk), "name": policy.name, "agent": agent_ref(policy.agent),
        "package": {"id": str(policy.package_id), "name": policy.package.name} if policy.package_id else None,
        "kind": policy.kind, "kind_label": policy.get_kind_display(), "amount_idr": policy.amount_idr, "percent": float(policy.percent),
        "trigger": policy.trigger, "trigger_label": policy.get_trigger_display(),
        "valid_from": policy.valid_from.isoformat() if policy.valid_from else None,
        "valid_until": policy.valid_until.isoformat() if policy.valid_until else None, "active": policy.active,
    }


def commission_payload(row):
    booking = row.booking
    return {
        "id": str(row.pk), "status": row.status, "status_label": row.get_status_display(), "agent": agent_ref(row.agent),
        "booking": {"id": str(booking.pk), "code": booking.code, "status": booking.status, "departure_code": booking.departure.code, "package_name": booking.departure.package.name},
        "policy": row.policy_snapshot_json, "pax": row.pax, "basis_idr": row.basis_idr, "amount_idr": row.amount_idr,
        "eligible_at": row.eligible_at.isoformat() if row.eligible_at else None,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None, "approved_by": _name(row.approved_by),
        "paid_on": row.paid_on.isoformat() if row.paid_on else None, "paid_by": _name(row.paid_by),
        "bank_account": f"{row.bank_account.bank_name} {row.bank_account.account_masked}" if row.bank_account_id else None,
        "reference": row.reference, "expense_id": str(row.expense_id) if row.expense_id else None,
        "reversed_at": row.reversed_at.isoformat() if row.reversed_at else None, "reverse_reason": row.reverse_reason,
        "review_note": row.review_note, "created_at": row.created_at.isoformat(),
    }


def history_payload(change):
    return {"id": str(change.pk), "from_agent": agent_ref(change.from_agent), "to_agent": agent_ref(change.to_agent), "reason": change.reason, "changed_by": _name(change.changed_by), "changed_at": change.created_at.isoformat()}


# ------------------------------------------------------------------ agen
class AgentSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32, required=False, allow_blank=True)
    name = serializers.CharField(max_length=160)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    business_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    bank_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    bank_account_name = serializers.CharField(max_length=160, required=False, allow_blank=True)
    bank_account_number = serializers.CharField(max_length=40, required=False, allow_blank=True, write_only=True)
    area = serializers.CharField(max_length=120, required=False, allow_blank=True)
    level = serializers.CharField(max_length=40, required=False, allow_blank=True)
    active = serializers.BooleanField(required=False)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True)

    def clean(self):
        data = {key: value.strip() if isinstance(value, str) else value for key, value in self.validated_data.items()}
        number = data.pop("bank_account_number", None)
        if number:  # nomor rekening asli tidak disimpan (sama dengan rekening travel)
            data["bank_account_masked"] = mask_account_number(number)
        return data


def _commission_total(statuses):
    rows = Commission.objects.filter(agent=OuterRef("pk"), status__in=statuses).order_by().values("agent").annotate(t=Sum("amount_idr")).values("t")
    return Subquery(rows)


def _agents():
    # Subquery per agregat: join booking × komisi akan menggandakan jumlah.
    bookings = Booking.objects.filter(agent=OuterRef("pk")).exclude(status__in=["DRAFT", "CANCELED", "EXPIRED"]).order_by().values("agent").annotate(n=Count("id")).values("n")
    return Agent.objects.annotate(
        booking_count=Subquery(bookings),
        commission_open_idr=_commission_total(["ESTIMATED", "ELIGIBLE", "APPROVED"]),
        commission_paid_idr=_commission_total(["PAID"]),
    )


def _agent_stats(agent):
    return {"booking_count": agent.booking_count or 0, "commission_open_idr": agent.commission_open_idr or 0, "commission_paid_idr": agent.commission_paid_idr or 0}


class AgentListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        return [IsAuthenticated(), require_permission("agents.manage" if self.request.method == "POST" else "agents.read")()]

    @extend_schema(operation_id="agents_list", responses=OpenApiTypes.OBJECT, parameters=[OpenApiParameter("q", str), OpenApiParameter("active", str, enum=["1", "0"]), OpenApiParameter("page", int)])
    def get(self, request):
        qs = _agents().filter(environment=resolve_active_environment(request.tenant))
        active = request.query_params.get("active", "")
        if active in {"1", "0"}:
            qs = qs.filter(active=active == "1")
        q = (request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(phone__icontains=q) | Q(area__icontains=q))
        return list_response(request, qs.order_by("-active", "name", "code"), lambda a: agent_payload(a, _agent_stats(a)))

    @extend_schema(request=AgentSerializer, responses={201: OpenApiTypes.OBJECT})
    @transaction.atomic
    def post(self, request):
        environment = resolve_active_environment(request.tenant)
        assert_environment_writable(request.tenant, environment)
        serializer = AgentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        agent = services.create_agent(tenant=request.tenant, environment=environment, data=serializer.clean(), actor=request.user)
        return Response(agent_payload(agent, {"booking_count": 0, "commission_open_idr": 0, "commission_paid_idr": 0}), status=status.HTTP_201_CREATED)


class AgentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        return [IsAuthenticated(), require_permission("agents.manage" if self.request.method == "PATCH" else "agents.read")()]

    def _get(self, request, agent_id):
        agent = _agents().filter(pk=agent_id, environment=resolve_active_environment(request.tenant)).first()
        if agent is None:
            raise NotFound("Agen tidak ditemukan.")
        return agent

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, agent_id):
        agent = self._get(request, agent_id)
        return Response(agent_payload(agent, _agent_stats(agent)))

    @extend_schema(request=AgentSerializer, responses=OpenApiTypes.OBJECT)
    @transaction.atomic
    def patch(self, request, agent_id):
        agent = self._get(request, agent_id)
        assert_environment_writable(request.tenant, agent.environment)
        serializer = AgentSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.clean()
        if "code" in data and not data["code"]:
            raise ValidationError({"code": "Kode agen tidak boleh kosong."})
        services.update_agent(agent=Agent.objects.get(pk=agent.pk), data=data, actor=request.user)
        agent = self._get(request, agent_id)
        return Response(agent_payload(agent, _agent_stats(agent)))


# ----------------------------------------------------------- kebijakan
class PolicySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    agent = serializers.UUIDField(required=False, allow_null=True)
    package = serializers.UUIDField(required=False, allow_null=True)
    kind = serializers.ChoiceField(choices=CommissionKind.choices)
    amount_idr = serializers.IntegerField(min_value=0, max_value=1_000_000_000, required=False, default=0)
    percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False, default=0)
    trigger = serializers.ChoiceField(choices=CommissionTrigger.choices, required=False, default=CommissionTrigger.DP_VERIFIED)
    valid_from = serializers.DateField(required=False, allow_null=True)
    valid_until = serializers.DateField(required=False, allow_null=True)
    active = serializers.BooleanField(required=False, default=True)

    def resolve(self, environment, instance=None):
        data = dict(self.validated_data)
        if data.get("agent"):
            data["agent"] = Agent.objects.filter(pk=data["agent"], environment=environment).first() or self._missing("agent", "Agen")
        if data.get("package"):
            data["package"] = TravelPackage.objects.filter(pk=data["package"], environment=environment).first() or self._missing("package", "Paket")
        merged = {field: getattr(instance, field) for field in ("kind", "amount_idr", "percent", "valid_from", "valid_until")} if instance else {}
        merged.update({key: value for key, value in data.items() if key in {"kind", "amount_idr", "percent", "valid_from", "valid_until"}})
        if merged.get("kind") == CommissionKind.FIXED_PER_PAX and not merged.get("amount_idr"):
            raise ValidationError({"amount_idr": "Isi nominal komisi per jamaah."})
        if merged.get("kind") == CommissionKind.PERCENT_NET and not merged.get("percent"):
            raise ValidationError({"percent": "Isi persentase komisi."})
        if merged.get("valid_from") and merged.get("valid_until") and merged["valid_until"] < merged["valid_from"]:
            raise ValidationError({"valid_until": "Tanggal akhir tidak boleh sebelum tanggal mulai."})
        return data

    @staticmethod
    def _missing(field, label):
        raise ValidationError({field: f"{label} tidak ditemukan di workspace ini."})


def _policies():
    return CommissionPolicy.objects.select_related("agent", "package")


class PolicyListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        return [IsAuthenticated(), require_permission("commissions.policies" if self.request.method == "POST" else "commissions.read")()]

    @extend_schema(operation_id="commission_policies_list", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        qs = _policies().filter(environment=resolve_active_environment(request.tenant)).order_by("-active", "name", "id")
        return list_response(request, qs, policy_payload)

    @extend_schema(request=PolicySerializer, responses={201: OpenApiTypes.OBJECT})
    @transaction.atomic
    def post(self, request):
        environment = resolve_active_environment(request.tenant)
        assert_environment_writable(request.tenant, environment)
        serializer = PolicySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        policy = CommissionPolicy.objects.create(tenant=request.tenant, environment=environment, **serializer.resolve(environment))
        log_event(action="commissions.policy_created", request=request, object_type="commission_policy", object_id=policy.pk, changes=policy_payload(policy))
        return Response(policy_payload(policy), status=status.HTTP_201_CREATED)


class PolicyDetailView(APIView):
    permission_classes = [IsAuthenticated, require_permission("commissions.policies")]

    @extend_schema(request=PolicySerializer, responses=OpenApiTypes.OBJECT, description="Perubahan kebijakan hanya berlaku untuk komisi baru; komisi yang sudah ada memakai snapshot.")
    @transaction.atomic
    def patch(self, request, policy_id):
        environment = resolve_active_environment(request.tenant)
        policy = _policies().filter(pk=policy_id, environment=environment).first()
        if policy is None:
            raise NotFound("Kebijakan tidak ditemukan.")
        assert_environment_writable(request.tenant, environment)
        serializer = PolicySerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for key, value in serializer.resolve(environment, policy).items():
            setattr(policy, key, value)
        policy.save()
        log_event(action="commissions.policy_updated", request=request, object_type="commission_policy", object_id=policy.pk, changes={"fields": sorted(request.data)})
        return Response(policy_payload(policy))


# ------------------------------------------------------------- komisi
def _commissions():
    return Commission.objects.select_related("agent", "booking__departure__package", "approved_by", "paid_by", "bank_account")


class CommissionListView(APIView):
    permission_classes = [IsAuthenticated, require_permission("commissions.read")]

    @extend_schema(operation_id="commissions_list", responses=OpenApiTypes.OBJECT, parameters=[OpenApiParameter("status", str, enum=CommissionStatus.values), OpenApiParameter("agent", OpenApiTypes.UUID), OpenApiParameter("booking", OpenApiTypes.UUID), OpenApiParameter("page", int)])
    def get(self, request):
        qs = scope_filter(_commissions(), request, "booking__branch").filter(environment=resolve_active_environment(request.tenant))
        params = request.query_params
        if params.get("status"):
            if params["status"] not in CommissionStatus.values:
                raise ValidationError({"status": "Status komisi tidak dikenal."})
            qs = qs.filter(status=params["status"])
        if params.get("agent"):
            qs = qs.filter(agent_id=_uuid(params["agent"], "agent"))
        if params.get("booking"):
            qs = qs.filter(booking_id=_uuid(params["booking"], "booking"))
        return list_response(request, qs.order_by("-created_at", "id"), commission_payload)


class CommissionSummaryView(APIView):
    permission_classes = [IsAuthenticated, require_permission("commissions.read")]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        qs = scope_filter(Commission.objects, request, "booking__branch").filter(environment=resolve_active_environment(request.tenant))
        rows = {row["status"]: row for row in qs.values("status").annotate(count=Count("id"), total=Sum("amount_idr"))}
        return Response({"statuses": [{"status": value, "label": label, "count": rows.get(value, {}).get("count", 0), "total_idr": rows.get(value, {}).get("total") or 0} for value, label in CommissionStatus.choices]})


class CommissionActionSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    reason = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")
    paid_on = serializers.DateField(required=False)
    bank_account = serializers.UUIDField(required=False, allow_null=True)
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")


class CommissionActionView(APIView):
    permission_classes = [IsAuthenticated]
    action = ""
    PERMISSIONS = {"approve": "commissions.approve", "pay": "commissions.pay", "reverse": "commissions.approve"}

    def get_permissions(self):
        return [IsAuthenticated(), require_permission(self.PERMISSIONS[self.action])()]

    @extend_schema(request=CommissionActionSerializer, responses=OpenApiTypes.OBJECT)
    @transaction.atomic
    def post(self, request, commission_id):
        commission = scope_filter(Commission.objects, request, "booking__branch").filter(pk=commission_id, environment=resolve_active_environment(request.tenant)).first()
        if commission is None:
            raise NotFound("Komisi tidak ditemukan.")
        assert_environment_writable(request.tenant, commission.environment)
        serializer = CommissionActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if self.action == "approve":
            services.approve_commission(commission_id=commission.pk, actor=request.user, note=data["note"])
        elif self.action == "pay":
            account = None
            if data.get("bank_account"):
                account = TravelBankAccount.objects.filter(pk=data["bank_account"]).first()
                if account is None:
                    raise ValidationError({"bank_account": "Rekening tidak ditemukan."})
            services.pay_commission(commission_id=commission.pk, actor=request.user, paid_on=data.get("paid_on") or tenant_today(request.tenant), bank_account=account, reference=data["reference"])
        else:
            services.reverse_commission(commission_id=commission.pk, actor=request.user, reason=data["reason"])
        return Response(commission_payload(_commissions().get(pk=commission.pk)))


# --------------------------------------------------------- agen booking
class BookingAgentSerializer(serializers.Serializer):
    agent = serializers.UUIDField(allow_null=True)
    reason = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")


class BookingAgentView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        return [IsAuthenticated(), require_permission("bookings.create" if self.request.method == "POST" else "bookings.read")()]

    def _payload(self, booking):
        commission = _commissions().filter(booking=booking).exclude(status=CommissionStatus.REVERSED).first()
        changes = BookingAgentChange.objects.filter(booking=booking).select_related("from_agent", "to_agent", "changed_by")[:50]
        return {"agent": agent_ref(booking.agent), "commission": commission_payload(commission) if commission else None, "history": [history_payload(c) for c in changes]}

    def _get(self, booking_id):
        booking = scope_filter(Booking.objects, self.request).select_related("agent").filter(pk=booking_id).first()
        if booking is None:
            raise NotFound("Booking tidak ditemukan.")
        return booking

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Agen booking, komisi aktif dan histori perubahan agen.")
    def get(self, request, booking_id):
        return Response(self._payload(self._get(booking_id)))

    @extend_schema(request=BookingAgentSerializer, responses=OpenApiTypes.OBJECT)
    @transaction.atomic
    def post(self, request, booking_id):
        booking = self._get(booking_id)
        assert_environment_writable(request.tenant, booking.environment)
        serializer = BookingAgentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.change_booking_agent(booking_id=booking.pk, agent_id=serializer.validated_data["agent"], reason=serializer.validated_data["reason"], actor=request.user)
        return Response(self._payload(self._get(booking_id)))
