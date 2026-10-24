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
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.booking.models import Booking
from modules.booking.serializers import (
    BookingCreateSerializer,
    BookingTransitionSerializer,
    BookingUpdateSerializer,
    booking_payload,
)
from modules.booking.services import create_booking, transition_booking, update_draft_booking
from modules.tenants.environment import assert_environment_writable, resolve_active_environment
from modules.tenants.rbac import require_permission


def _get_booking(booking_id) -> Booking:
    try:
        return Booking.objects.select_related("departure", "departure__package").get(pk=booking_id)
    except (Booking.DoesNotExist, ValueError, DjangoValidationError):
        raise NotFound("Booking tidak ditemukan.") from None


class BookingListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), require_permission("bookings.create")()]
        return [IsAuthenticated(), require_permission("bookings.read")()]

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
            qs.select_related("departure", "departure__package", "created_by", "canceled_by")
            .prefetch_related("participants__pilgrim", "price_lines")
            .order_by("-booked_at", "code")[:200]
        )
        return Response({"results": [booking_payload(b) for b in rows]})

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
                notes=serializer.validated_data.get("notes", ""),
                allow_duplicate=serializer.validated_data.get("allow_duplicate", False),
                actor=request.user,
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
        if self.request.method == "PATCH":
            return [IsAuthenticated(), require_permission("bookings.create")()]
        return [IsAuthenticated(), require_permission("bookings.read")()]

    def get(self, request, booking_id):
        booking = _get_booking(booking_id)
        return Response(booking_payload(booking))

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
                notes=validated.get("notes") if "notes" in validated else None,
                allow_duplicate=validated.get("allow_duplicate", False),
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


class BookingTransitionView(APIView):
    """POST /bookings/{id}/transition — guard MOD-07 + §6.2 (UI-07)."""

    permission_classes = [IsAuthenticated, require_permission("bookings.create")]

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
