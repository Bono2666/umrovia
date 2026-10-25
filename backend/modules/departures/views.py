"""Keberangkatan — Spec §8.3 (GET/POST /departures, GET/PATCH /departures/{id},
POST /departures/{id}/transition; UI-05).

Seat: `seats_taken` TIDAK pernah masuk payload input — hanya lewat layanan
atomik `services.reserve_seats/release_seats` (BR-002/UAT-02, dipakai booking
S09). `seat_capacity`/`seats_blocked` boleh diedit dengan guard invariant
(serah serializer) — menaikkan kapasitas aman, menurunkan di bawah
terpakai+terblokir ditolak 400.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.departures.models import Departure, generate_departure_code
from modules.departures.serializers import (
    DepartureTransitionSerializer,
    DepartureWriteSerializer,
    departure_payload,
)
from modules.departures.services import transition_departure
from modules.tenants.environment import assert_environment_writable, resolve_active_environment
from modules.tenants.models import MembershipStatus, TenantMembership
from modules.tenants.rbac import require_permission


def _get_departure(departure_id) -> Departure:
    try:
        return Departure.objects.get(pk=departure_id)
    except (Departure.DoesNotExist, ValueError, ValidationError):
        raise NotFound("Keberangkatan tidak ditemukan.") from None


class DepartureStaffView(APIView):
    """Pemilih PIC; tidak membuka role, grant, atau daftar staf tenant lain."""

    permission_classes = [IsAuthenticated, require_permission("departures.write")]

    def get(self, request):
        staff = (
            TenantMembership.objects.filter(status=MembershipStatus.ACTIVE, user__status="ACTIVE")
            .select_related("user").order_by("user__full_name", "user__email")
        )
        return Response({"results": [
            {"id": str(row.user_id), "name": row.user.full_name or row.user.email}
            for row in staff
        ]})


class DepartureListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), require_permission("departures.write")()]
        return [IsAuthenticated(), require_permission("departures.read")()]

    def get(self, request):
        qs = Departure.objects.all()
        env = request.query_params.get("environment", "").strip()
        if env:
            from modules.tenants.models import Environment

            if env not in Environment.values:
                raise ValidationError({"environment": "Nilai tidak dikenal (demo/production)."})
            qs = qs.filter(environment=env)
        status_filter = request.query_params.get("status", "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        package_filter = request.query_params.get("package", "").strip()
        if package_filter:
            qs = qs.filter(package_id=package_filter)
        q = request.query_params.get("q", "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(
                Q(code__icontains=q)
                | Q(city_of_origin__icontains=q)
                | Q(package__name__icontains=q)
                | Q(package__code__icontains=q)
            )
        rows = qs.select_related("package", "lead_staff").prefetch_related("package__room_prices").order_by("start_at", "code")[:200]
        return Response({"results": [departure_payload(d) for d in rows]})

    def post(self, request):
        serializer = DepartureWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        environment = resolve_active_environment(request.tenant)
        assert_environment_writable(request.tenant, environment)
        if serializer.validated_data["package"].environment != environment:
            # Integritas §5.2: referensi lintas-environment ditolak di aplikasi
            # (FK komposit DB menyusul bila diperlukan).
            raise ValidationError(
                {"package": f"Paket harus berasal dari environment aktif '{environment}'."}
            )

        dep = Departure(tenant=request.tenant, environment=environment)
        for _attempt in range(3):
            dep.code = generate_departure_code()
            for field, value in serializer.validated_data.items():
                setattr(dep, field, value)
            try:
                with transaction.atomic():
                    dep.save()
            except IntegrityError:
                continue  # tabrakan kode / CHECK seat → coba sekali lagi
            break
        else:
            raise ValidationError({"code": "Gagal membuat keberangkatan, coba lagi."})

        log_event(
            action="departures.created",
            request=request,
            object_type="departure",
            object_id=dep.pk,
            changes={
                "code": dep.code,
                "package": dep.package.code,
                "start_at": dep.start_at.isoformat(),
                "seat_capacity": dep.seat_capacity,
            },
        )
        return Response(departure_payload(dep), status=status.HTTP_201_CREATED)


class DepartureDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsAuthenticated(), require_permission("departures.write")()]
        return [IsAuthenticated(), require_permission("departures.read")()]

    def get(self, request, departure_id):
        return Response(departure_payload(_get_departure(departure_id)))

    def patch(self, request, departure_id):
        dep = _get_departure(departure_id)
        assert_environment_writable(request.tenant, dep.environment)
        serializer = DepartureWriteSerializer(dep, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if "package" in serializer.validated_data:
            package = serializer.validated_data["package"]
            if package.environment != dep.environment:
                raise ValidationError(
                    {"package": f"Paket harus berasal dari environment '{dep.environment}'."}
                )
        before_capacity = dep.seat_capacity
        for field, value in serializer.validated_data.items():
            setattr(dep, field, value)
        try:
            dep.save()
        except IntegrityError:
            # CHECK ck_departure_seats_within_capacity (BR-002) — pengaman DB
            raise ValidationError(
                {"seat_capacity": "Kapasitas tidak boleh di bawah kursi terpakai + terblokir."}
            ) from None

        changes = {"code": dep.code, "fields": sorted(set(request.data.keys()))}
        if dep.seat_capacity != before_capacity:
            changes["seat_capacity"] = [before_capacity, dep.seat_capacity]
        log_event(
            action="departures.updated",
            request=request,
            object_type="departure",
            object_id=dep.pk,
            changes=changes,
        )
        return Response(departure_payload(dep))


class DepartureTransitionView(APIView):
    """POST /departures/{id}/transition — guard state machine §6.5 (UI-05)."""

    permission_classes = [IsAuthenticated, require_permission("departures.manage")]

    def post(self, request, departure_id):
        dep = _get_departure(departure_id)
        assert_environment_writable(request.tenant, dep.environment)
        serializer = DepartureTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        prior = dep.status
        checklist_exception = bool(serializer.validated_data.get("checklist_exception"))
        try:
            transition_departure(
                departure=dep,
                target=serializer.validated_data["target"],
                actor=request.user,
                reason=serializer.validated_data.get("reason") or "",
                checklist_exception=checklist_exception,
            )
        except DjangoValidationError as exc:
            # service memakai DjangoValidationError (domain) → petakan ke DRF 400
            raise ValidationError(
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            ) from exc

        changes = {
            "code": dep.code,
            "transition": [prior, dep.status],
            **(
                {"reason": serializer.validated_data["reason"]}
                if serializer.validated_data.get("reason")
                else {}
            ),
        }
        if checklist_exception:
            # jejak *approved exception* §6.5/OPS02 di audit
            changes["checklist_exception"] = True
        log_event(
            action="departures.transitioned",
            request=request,
            object_type="departure",
            object_id=dep.pk,
            changes=changes,
        )
        return Response(departure_payload(dep))
