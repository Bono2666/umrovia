"""Booking — Spec §8.3 (GET/POST /bookings Sales/Admin, GET/PATCH
/bookings/{id} scoped staff "update draft", POST /bookings/{id}/transition;
UI-07).

- GET: filter `status`, `departure`, `q` (kode booking / nama & kode jamaah),
  `environment`.
- POST: buat DRAFT dengan peserta unik (UAT-03) + snapshot harga (UAT-04);
  kuota trial dikonsumsi per peserta (POL-08).
- PATCH: hanya DRAFT (draft-only §8.3).
- transition: guard MOD-07 + peserta §6.2 + kursi atomik (UAT-02 booking).
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.api import list_response
from modules.audit.services import log_event
from modules.booking.models import Booking
from modules.booking.serializers import (
    BookingCreateSerializer,
    BookingTransitionSerializer,
    BookingUpdateSerializer,
    booking_payload,
)
from modules.booking.services import (
    UNSET,
    create_booking,
    delete_draft_booking,
    transition_booking,
    update_draft_booking,
)
from modules.catalog.models import RoomType
from modules.tenants.branches import default_branch, resolve_branch
from modules.tenants.environment import assert_environment_writable, resolve_active_environment
from modules.tenants.rbac import has_permission, permission_list, require_permission


def _uuid_param(value, field):
    from uuid import UUID

    try:
        return UUID(value)
    except ValueError:
        raise ValidationError({field: "ID tidak valid."}) from None


def _can_discount(request) -> bool:
    return has_permission(permission_list(request.membership.role), "bookings.discount")


def _get_booking(booking_id) -> Booking:
    try:
        return Booking.objects.select_related("departure", "departure__package", "agent", "branch").get(pk=booking_id)
    except (Booking.DoesNotExist, ValueError, DjangoValidationError):
        raise NotFound("Booking tidak ditemukan.") from None


class BookingListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), require_permission("bookings.create")()]
        return [IsAuthenticated(), require_permission("bookings.read")()]

    @extend_schema(operation_id="bookings_list", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        qs = Booking.objects.all()
        env = request.query_params.get("environment", "").strip()
        if env:
            from modules.tenants.models import Environment

            if env not in Environment.values:
                raise ValidationError({"environment": "Nilai tidak dikenal (demo/production)."})
            qs = qs.filter(environment=env)
        status_filter = request.query_params.get("status", "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        branch_filter = request.query_params.get("branch", "").strip()
        if branch_filter:
            qs = qs.filter(branch_id=_uuid_param(branch_filter, "branch"))
        departure_filter = request.query_params.get("departure", "").strip()
        if departure_filter:
            qs = qs.filter(departure_id=departure_filter)
        q = request.query_params.get("q", "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(
                Q(code__icontains=q)
                | Q(participants__pilgrim__name__icontains=q)
                | Q(participants__pilgrim__code__icontains=q)
            ).distinct()
        rows = (
            qs.select_related("departure", "departure__package", "created_by", "canceled_by", "agent", "branch")
            .prefetch_related("participants__pilgrim", "price_lines")
            .order_by("-booked_at", "code")
        )
        return list_response(request, rows, booking_payload)

    @extend_schema(request=BookingCreateSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        environment = resolve_active_environment(request.tenant)
        assert_environment_writable(request.tenant, environment)

        try:
            booking = create_booking(
                tenant=request.tenant,
                environment=environment,
                departure_id=serializer.validated_data["departure"].pk,
                pilgrim_ids=serializer.validated_data["participants"],
                room_types=serializer.validated_data.get("room_types"),
                notes=serializer.validated_data.get("notes", ""),
                allow_duplicate=serializer.validated_data.get("allow_duplicate", False),
                actor=request.user,
                payer_name=serializer.validated_data.get("payer_name", ""),
                agent_id=serializer.validated_data.get("agent"),
                adjustments=serializer.validated_data.get("adjustments"),
                can_discount=_can_discount(request),
                branch=resolve_branch(serializer.validated_data.get("branch")) if "branch" in request.data else default_branch(request),
                price_categories=serializer.validated_data.get("price_categories"),
                addons=serializer.validated_data.get("addons"),
            )
        except DjangoValidationError as exc:
            # service memakai DjangoValidationError (domain) → petakan ke DRF 400
            raise ValidationError(
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            ) from exc

        log_event(
            action="bookings.created",
            request=request,
            object_type="booking",
            object_id=booking.pk,
            changes={
                "code": booking.code,
                "departure": booking.departure.code,
                "participants": booking.participant_count,
            },
        )
        return Response(booking_payload(booking), status=status.HTTP_201_CREATED)


class BookingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method in {"PATCH", "DELETE"}:
            return [IsAuthenticated(), require_permission("bookings.create")()]
        return [IsAuthenticated(), require_permission("bookings.read")()]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, booking_id):
        booking = _get_booking(booking_id)
        return Response(booking_payload(booking))

    @extend_schema(request=BookingUpdateSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request, booking_id):
        booking = _get_booking(booking_id)
        assert_environment_writable(request.tenant, booking.environment)
        serializer = BookingUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        try:
            booking = update_draft_booking(
                booking_id=booking.pk,
                environment=booking.environment,
                departure_id=validated["departure"].pk if "departure" in validated else None,
                pilgrim_ids=validated.get("participants"),
                room_types=validated.get("room_types"),
                notes=validated.get("notes") if "notes" in validated else None,
                allow_duplicate=validated.get("allow_duplicate", False),
                payer_name=validated.get("payer_name"),
                agent_id=validated["agent"] if "agent" in validated else UNSET,
                adjustments=validated.get("adjustments"),
                can_discount=_can_discount(request),
                actor=request.user,
                branch=resolve_branch(validated["branch"]) if "branch" in validated else UNSET,
                price_categories=validated.get("price_categories"),
                addons=validated.get("addons"),
            )
        except DjangoValidationError as exc:
            raise ValidationError(
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            ) from exc

        log_event(
            action="bookings.updated",
            request=request,
            object_type="booking",
            object_id=booking.pk,
            changes={"code": booking.code, "fields": sorted(set(request.data.keys()))},
        )
        booking = _get_booking(booking.pk)
        return Response(booking_payload(booking))

    @extend_schema(responses={204: None}, description="Hapus booking DRAF (belum menahan kursi, belum ada invoice). Kuota trial yang terpakai tidak dikembalikan (TR03).")
    def delete(self, request, booking_id):
        booking = _get_booking(booking_id)
        assert_environment_writable(request.tenant, booking.environment)
        try:
            code = delete_draft_booking(booking_id=booking.pk)
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages) from exc
        log_event(action="bookings.deleted", request=request, object_type="booking", object_id=booking.pk, changes={"code": code})
        return Response(status=204)


class BookingTransitionView(APIView):
    """POST /bookings/{id}/transition — guard MOD-07 + §6.2 (UI-07)."""

    permission_classes = [IsAuthenticated, require_permission("bookings.create")]

    @extend_schema(request=BookingTransitionSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, booking_id):
        booking = _get_booking(booking_id)
        assert_environment_writable(request.tenant, booking.environment)
        serializer = BookingTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        prior = booking.status
        try:
            booking = transition_booking(
                booking_id=booking.pk,
                target=serializer.validated_data["target"],
                reason=serializer.validated_data.get("reason") or "",
                actor=request.user,
            )
        except DjangoValidationError as exc:
            raise ValidationError(
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            ) from exc

        changes = {"code": booking.code, "transition": [prior, booking.status]}
        reason = serializer.validated_data.get("reason")
        if reason:
            changes["reason"] = reason
        log_event(
            action="bookings.transitioned",
            request=request,
            object_type="booking",
            object_id=booking.pk,
            changes=changes,
        )
        booking = _get_booking(booking.pk)
        return Response(booking_payload(booking))


# ------------------------------------------------------------ daftar tunggu --
def waitlist_payload(entry, position=None) -> dict:
    from modules.booking.services import waitlist_position

    dep = entry.departure
    return {
        "id": str(entry.pk), "status": entry.status, "status_label": entry.get_status_display(),
        "position": (position if position is not None else waitlist_position(entry)) if entry.status == "WAITING" else None,
        "departure": {"id": str(dep.pk), "code": dep.code, "package_name": dep.package.name, "start_at": dep.start_at.isoformat(), "available_seats": dep.available_seats},
        "pilgrim": {"id": str(entry.pilgrim_id), "code": entry.pilgrim.code, "name": entry.pilgrim.name, "phone": entry.pilgrim.phone},
        "room_type": entry.room_type, "notes": entry.notes, "cancel_reason": entry.cancel_reason,
        "booking": {"id": str(entry.booking_id), "code": entry.booking.code} if entry.booking_id else None,
        "created_at": entry.created_at.isoformat(),
        "created_by_name": (entry.created_by.full_name or entry.created_by.email) if entry.created_by_id else None,
    }


class WaitlistSerializer(serializers.Serializer):
    departure = serializers.UUIDField()
    pilgrim = serializers.UUIDField()
    room_type = serializers.ChoiceField(choices=RoomType.choices, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=240, required=False, allow_blank=True, default="")


class WaitlistListCreateView(APIView):
    def get_permissions(self):
        return [IsAuthenticated(), require_permission("bookings.create" if self.request.method == "POST" else "bookings.read")()]

    @extend_schema(operation_id="waitlist_list", responses=OpenApiTypes.OBJECT, description="Daftar tunggu per keberangkatan, urut waktu masuk (`?departure=`, `?status=WAITING|BOOKED|CANCELED`).")
    def get(self, request):
        from modules.booking.models import WaitlistEntry, WaitlistStatus

        qs = WaitlistEntry.objects.filter(environment=resolve_active_environment(request.tenant)).select_related("departure__package", "pilgrim", "booking", "created_by")
        status_filter = request.query_params.get("status", "WAITING")
        if status_filter:
            if status_filter not in WaitlistStatus.values:
                raise ValidationError({"status": "Status tidak dikenal."})
            qs = qs.filter(status=status_filter)
        if request.query_params.get("departure"):
            qs = qs.filter(departure_id=_uuid_param(request.query_params["departure"], "departure"))
        rows = list(qs.order_by("departure__start_at", "departure_id", "created_at")[:500])
        positions, seen = {}, {}
        for row in rows:
            if row.status == WaitlistStatus.WAITING:
                seen[row.departure_id] = seen.get(row.departure_id, 0) + 1
                positions[row.pk] = seen[row.departure_id]
        return Response({"results": [waitlist_payload(r, positions.get(r.pk)) for r in rows]})

    @extend_schema(request=WaitlistSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        from modules.booking.services import add_to_waitlist

        environment = resolve_active_environment(request.tenant)
        assert_environment_writable(request.tenant, environment)
        serializer = WaitlistSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            entry = add_to_waitlist(tenant=request.tenant, environment=environment, departure_id=data["departure"], pilgrim_id=data["pilgrim"], room_type=data["room_type"], notes=data["notes"], actor=request.user)
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages) from exc
        log_event(action="waitlist.added", request=request, object_type="waitlist_entry", object_id=entry.pk, changes={"departure": entry.departure.code, "pilgrim": str(entry.pilgrim_id)})
        return Response(waitlist_payload(entry), status=status.HTTP_201_CREATED)


class WaitlistActionView(APIView):
    permission_classes = [IsAuthenticated, require_permission("bookings.create")]
    action = "book"

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT, description="`book` membuat booking DRAF dari entri (urut antrean); `cancel` wajib `reason`.")
    def post(self, request, entry_id):
        from modules.booking.models import WaitlistEntry
        from modules.booking.services import book_from_waitlist, cancel_waitlist

        entry = WaitlistEntry.objects.filter(pk=entry_id, environment=resolve_active_environment(request.tenant)).first()
        if entry is None:
            raise NotFound("Entri daftar tunggu tidak ditemukan.")
        assert_environment_writable(request.tenant, entry.environment)
        try:
            if self.action == "book":
                entry = book_from_waitlist(entry_id=entry.pk, actor=request.user, branch=default_branch(request))
            else:
                entry = cancel_waitlist(entry_id=entry.pk, reason=str(request.data.get("reason") or ""))
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages) from exc
        log_event(action=f"waitlist.{'booked' if self.action == 'book' else 'canceled'}", request=request, object_type="waitlist_entry", object_id=entry.pk, changes={"booking": entry.booking.code if entry.booking_id else None})
        entry = WaitlistEntry.objects.select_related("departure__package", "pilgrim", "booking", "created_by").get(pk=entry.pk)
        return Response(waitlist_payload(entry))
