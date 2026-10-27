"""API CRM & Lead (MOD-19): /leads … Grant `leads.manage` (Owner, Admin, Sales); konversi juga `pilgrims.write`."""
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.api import list_response
from modules.audit.services import log_event
from modules.catalog.models import TravelPackage
from modules.crm import services
from modules.crm.models import OPEN_STAGES, ActivityKind, Lead, LeadSource, LeadStage
from modules.departures.models import Departure
from modules.pilgrims.crypto import normalize_phone
from modules.tenants.environment import assert_environment_writable, resolve_active_environment
from modules.tenants.models import MembershipStatus, TenantMembership
from modules.tenants.rbac import has_permission, permission_list, require_permission

LIST_PARAMS = [
    OpenApiParameter("stage", str, enum=LeadStage.values), OpenApiParameter("source", str, enum=LeadSource.values),
    OpenApiParameter("owner", str, description="`me` atau UUID pengguna"), OpenApiParameter("follow_up", str, enum=["due", "overdue"]),
    OpenApiParameter("q", str), OpenApiParameter("page", int),
]


def _name(user):
    return (user.full_name or user.email) if user else None


def lead_payload(lead, *, detail=False):
    data = {
        "id": str(lead.pk), "code": lead.code, "environment": lead.environment, "name": lead.name, "phone": lead.phone, "email": lead.email,
        "city": lead.city, "source": lead.source, "source_label": lead.get_source_display(), "pax": lead.pax, "notes": lead.notes,
        "interest_package": {"id": str(lead.interest_package_id), "name": lead.interest_package.name} if lead.interest_package_id else None,
        "interest_departure": {"id": str(lead.interest_departure_id), "code": lead.interest_departure.code, "start_at": lead.interest_departure.start_at.isoformat()} if lead.interest_departure_id else None,
        "stage": lead.stage, "stage_label": lead.get_stage_display(), "stage_changed_at": lead.stage_changed_at.isoformat(), "lost_reason": lead.lost_reason,
        "owner": {"id": str(lead.owner_id), "name": _name(lead.owner)} if lead.owner_id else None,
        "next_follow_up_at": lead.next_follow_up_at.isoformat() if lead.next_follow_up_at else None,
        "follow_up_overdue": bool(lead.next_follow_up_at and lead.next_follow_up_at < timezone.now() and lead.stage in OPEN_STAGES),
        "converted_pilgrim": {"id": str(lead.converted_pilgrim_id), "code": lead.converted_pilgrim.code, "name": lead.converted_pilgrim.name} if lead.converted_pilgrim_id else None,
        "converted_at": lead.converted_at.isoformat() if lead.converted_at else None, "created_at": lead.created_at.isoformat(),
        "deletable": lead.converted_pilgrim_id is None,
    }
    if detail:
        data["activities"] = [{"id": str(a.pk), "kind": a.kind, "kind_label": a.get_kind_display(), "body": a.body, "actor": _name(a.actor), "created_at": a.created_at.isoformat()}
                              for a in lead.activities.select_related("actor")[:50]]
        data["duplicates"] = services.duplicates(environment=lead.environment, phone=lead.phone, email=lead.email, exclude=lead.pk)
    return data


def _leads():
    return Lead.objects.select_related("interest_package", "interest_departure", "owner", "converted_pilgrim")


def _get(lead_id):
    lead = _leads().filter(pk=lead_id).first()
    if lead is None:
        raise NotFound("Lead tidak ditemukan.")
    return lead


class LeadSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    city = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    source = serializers.ChoiceField(choices=LeadSource.choices, required=False, default=LeadSource.OTHER)
    interest_package = serializers.UUIDField(required=False, allow_null=True, default=None)
    interest_departure = serializers.UUIDField(required=False, allow_null=True, default=None)
    pax = serializers.IntegerField(min_value=1, max_value=100, required=False, default=1)
    notes = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    owner = serializers.UUIDField(required=False, allow_null=True, default=None)
    next_follow_up_at = serializers.DateTimeField(required=False, allow_null=True, default=None)

    def validate_phone(self, value):
        phone = normalize_phone(value)
        if phone and not 9 <= len(phone) - 1 <= 15:
            raise serializers.ValidationError("Nomor telepon tidak valid.")
        return phone

    def resolve(self, request, environment):
        """UUID → objek milik tenant & environment yang sama (tolak ID asing)."""
        data = dict(self.validated_data)
        if data.get("interest_package"):
            data["interest_package"] = TravelPackage.objects.filter(pk=data["interest_package"], environment=environment).first() or self._missing("interest_package", "Paket")
        if data.get("interest_departure"):
            data["interest_departure"] = Departure.objects.filter(pk=data["interest_departure"], environment=environment).first() or self._missing("interest_departure", "Keberangkatan")
        if data.get("owner"):
            member = TenantMembership.objects.filter(tenant=request.tenant, user_id=data["owner"], status=MembershipStatus.ACTIVE).select_related("user").first()
            data["owner"] = member.user if member else self._missing("owner", "Staf")
        return data

    @staticmethod
    def _missing(field, label):
        raise ValidationError({field: f"{label} tidak ditemukan di workspace ini."})


class LeadListCreateView(APIView):
    permission_classes = [IsAuthenticated, require_permission("leads.manage")]

    @extend_schema(parameters=LIST_PARAMS, responses=OpenApiTypes.OBJECT, description="Lead workspace aktif. `?page=` untuk paginasi (50/halaman).")
    def get(self, request):
        params = request.query_params
        qs = _leads().filter(environment=resolve_active_environment(request.tenant))
        for field, choices in (("stage", LeadStage), ("source", LeadSource)):
            value = params.get(field, "")
            if value == "open" and field == "stage":
                qs = qs.filter(stage__in=OPEN_STAGES)
            elif value:
                if value not in choices.values:
                    raise ValidationError({field: "Nilai filter tidak dikenal."})
                qs = qs.filter(**{field: value})
        owner = params.get("owner", "")
        if owner == "me":
            qs = qs.filter(owner=request.user)
        elif owner:
            try:
                qs = qs.filter(owner_id=UUID(owner))
            except ValueError:
                raise ValidationError({"owner": "Pemilik tidak valid."}) from None
        follow_up = params.get("follow_up", "")
        if follow_up:
            if follow_up not in {"due", "overdue"}:
                raise ValidationError({"follow_up": "Pilih due atau overdue."})
            limit = timezone.now() if follow_up == "overdue" else services.local_day_end(request.tenant)
            qs = qs.filter(stage__in=OPEN_STAGES, next_follow_up_at__lt=limit).order_by("next_follow_up_at", "id")
        else:
            qs = qs.order_by("-created_at", "id")
        q = (params.get("q") or "").strip()
        if q:
            digits = "".join(ch for ch in q if ch.isdigit())
            match = Q(name__icontains=q) | Q(code__icontains=q) | Q(email__icontains=q) | Q(city__icontains=q)
            if len(digits) >= 4:
                match |= Q(phone__contains=digits[1:] if digits.startswith("0") else digits)
            qs = qs.filter(match)
        return list_response(request, qs, lead_payload)

    @extend_schema(request=LeadSerializer, responses={201: OpenApiTypes.OBJECT}, description="Telepon/email yang sudah ada → 400 `duplicates` kecuali `allow_duplicate=true`.")
    @transaction.atomic
    def post(self, request):
        environment = resolve_active_environment(request.tenant)
        assert_environment_writable(request.tenant, environment)
        serializer = LeadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lead = services.create_lead(tenant=request.tenant, environment=environment, actor=request.user, data=serializer.resolve(request, environment),
                                    allow_duplicate=str(request.data.get("allow_duplicate", "")).lower() in {"true", "1"})
        return Response(lead_payload(_get(lead.pk), detail=True), status=status.HTTP_201_CREATED)


class LeadSummaryView(APIView):
    permission_classes = [IsAuthenticated, require_permission("leads.manage")]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Funnel per tahap, tingkat konversi (jadi ÷ (jadi + tidak jadi)), follow-up, sumber.")
    def get(self, request):
        return Response(services.summary(request.tenant, resolve_active_environment(request.tenant)))


class LeadOwnersView(APIView):
    permission_classes = [IsAuthenticated, require_permission("leads.manage")]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Staf aktif yang dapat menjadi pemilik lead.")
    def get(self, request):
        members = TenantMembership.objects.filter(tenant=request.tenant, status=MembershipStatus.ACTIVE).select_related("user", "role").order_by("user__full_name", "user__email")
        rows = [{"id": str(m.user_id), "name": _name(m.user)} for m in members if has_permission(permission_list(m.role), "leads.manage")]
        return Response({"results": rows})


class LeadDetailView(APIView):
    permission_classes = [IsAuthenticated, require_permission("leads.manage")]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, lead_id):
        return Response(lead_payload(_get(lead_id), detail=True))

    @extend_schema(request=LeadSerializer, responses=OpenApiTypes.OBJECT, description="Ubah data lead (tahap diubah lewat /stage).")
    @transaction.atomic
    def patch(self, request, lead_id):
        lead = _get(lead_id)
        assert_environment_writable(request.tenant, lead.environment)
        serializer = LeadSerializer(data={**lead_payload(lead, detail=False), **request.data, "interest_package": request.data.get("interest_package", lead.interest_package_id),
                                          "interest_departure": request.data.get("interest_departure", lead.interest_departure_id), "owner": request.data.get("owner", lead.owner_id)})
        serializer.is_valid(raise_exception=True)
        data = serializer.resolve(request, lead.environment)
        changed = sorted(key for key in request.data if key in data)
        if "next_follow_up_at" in changed and data["next_follow_up_at"] and lead.stage not in OPEN_STAGES:
            raise ValidationError({"next_follow_up_at": "Lead yang sudah selesai tidak perlu follow-up."})
        for key in changed:
            setattr(lead, key, data[key])
        lead.save()
        log_event(action="leads.updated", request=request, object_type="lead", object_id=lead.pk, changes={"code": lead.code, "fields": changed})
        return Response(lead_payload(_get(lead.pk), detail=True))

    @transaction.atomic
    def delete(self, request, lead_id):
        lead = _get(lead_id)
        assert_environment_writable(request.tenant, lead.environment)
        if lead.converted_pilgrim_id:
            raise ValidationError({"lead": "Lead yang sudah menjadi jamaah tidak dapat dihapus."})
        log_event(action="leads.deleted", request=request, object_type="lead", object_id=lead.pk, changes={"code": lead.code})
        lead.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class LeadStageView(APIView):
    permission_classes = [IsAuthenticated, require_permission("leads.manage")]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT, description="Pindah tahap; LOST wajib `lost_reason`; WON hanya lewat konversi.")
    def post(self, request, lead_id):
        lead = _get(lead_id)
        assert_environment_writable(request.tenant, lead.environment)
        services.change_stage(lead, stage=str(request.data.get("stage", "")), actor=request.user, lost_reason=str(request.data.get("lost_reason", "")))
        return Response(lead_payload(_get(lead.pk), detail=True))


class ActivitySerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[ActivityKind.NOTE, ActivityKind.CALL, ActivityKind.WHATSAPP, ActivityKind.MEETING])
    body = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    next_follow_up_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    clear_follow_up = serializers.BooleanField(required=False, default=False)


class LeadActivityView(APIView):
    permission_classes = [IsAuthenticated, require_permission("leads.manage")]

    @extend_schema(request=ActivitySerializer, responses={201: OpenApiTypes.OBJECT}, description="Catat aktivitas; kontak pertama memindahkan NEW → CONTACTED; opsional jadwal follow-up berikutnya.")
    def post(self, request, lead_id):
        lead = _get(lead_id)
        assert_environment_writable(request.tenant, lead.environment)
        serializer = ActivitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.add_activity(lead, actor=request.user, **serializer.validated_data)
        return Response(lead_payload(_get(lead.pk), detail=True), status=status.HTTP_201_CREATED)


class LeadConvertView(APIView):
    permission_classes = [IsAuthenticated, require_permission("leads.manage"), require_permission("pilgrims.write")]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT, description="Jadikan jamaah baru (atau tautkan `pilgrim` yang sudah ada); tahap WON. Idempoten.")
    def post(self, request, lead_id):
        lead = _get(lead_id)
        assert_environment_writable(request.tenant, lead.environment)
        lead, pilgrim = services.convert(lead, actor=request.user, pilgrim_id=request.data.get("pilgrim") or None)
        return Response({**lead_payload(_get(lead.pk), detail=True), "pilgrim": {"id": str(pilgrim.pk), "code": pilgrim.code, "name": pilgrim.name}})
