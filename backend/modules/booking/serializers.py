"""Serializer booking (Spec §8.3, UI-07) + transisi status."""
from rest_framework import serializers

from modules.booking.models import Booking, BookingStatus
from modules.departures.models import Departure


def participant_payload(row) -> dict:
    return {
        "id": str(row.id),
        "pilgrim_id": str(row.pilgrim_id),
        "pilgrim_code": row.pilgrim.code,
        "pilgrim_name": row.pilgrim.name,
        "booking_passenger_id": str(row.booking_passenger_id),
        "participant_status": row.participant_status,
        "saas_charge_state": row.saas_charge_state,
        "dp_eligible_at": row.dp_eligible_at.isoformat() if row.dp_eligible_at else None,
        "pricing_snapshot": row.pricing_snapshot_json,
    }


def price_line_payload(row) -> dict:
    return {
        "id": str(row.id),
        "item_type": row.item_type,
        "description": row.description,
        "qty": row.qty,
        "unit_price": float(row.unit_price),
        "amount": float(row.amount),
    }


def booking_payload(booking: Booking) -> dict:
    """Payload booking — peserta + baris harga ikut untuk list & detail
    (list dibatasi 200 baris, §8.3)."""
    dep = booking.departure
    participants = list(booking.participants.all())
    lines = list(booking.price_lines.all())
    total = sum((line.amount for line in lines), start=0)
    return {
        "id": str(booking.id),
        "environment": booking.environment,
        "code": booking.code,
        "departure_id": str(dep.id),
        "departure_code": dep.code,
        "departure_start_at": dep.start_at.isoformat(),
        "departure_status": dep.status,
        "available_seats": dep.available_seats,
        "package_id": str(dep.package_id),
        "package_code": dep.package.code,
        "package_name": dep.package.name,
        "status": booking.status,
        "booked_at": booking.booked_at.isoformat(),
        "notes": booking.notes,
        "cancel_reason": booking.cancel_reason,
        "canceled_by_name": (
            (booking.canceled_by.full_name or booking.canceled_by.email) if booking.canceled_by_id else None
        ),
        "created_by_name": (
            (booking.created_by.full_name or booking.created_by.email) if booking.created_by_id else None
        ),
        "participant_count": len(participants),
        "participants": [participant_payload(p) for p in participants],
        "price_lines": [price_line_payload(line) for line in lines],
        "total_amount": float(total),
    }


class BookingCreateSerializer(serializers.Serializer):
    """POST /bookings — pilih keberangkatan + daftar jamaah (UI-07, UAT-03)."""

    # queryset = Manager sendiri (bukan .all() — context tenant belum ada di
    # class body); dievaluasi DRF saat validasi → ref lintas-tenant ditolak 400.
    departure = serializers.PrimaryKeyRelatedField(queryset=Departure.objects)
    participants = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    allow_duplicate = serializers.BooleanField(required=False, default=False)

    def validate_participants(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Jamaah yang sama tidak boleh dua kali dalam satu booking.")
        return value


class BookingUpdateSerializer(serializers.Serializer):
    """PATCH /bookings/{id} — hanya selama DRAFT (§8.3 update draft)."""

    departure = serializers.PrimaryKeyRelatedField(queryset=Departure.objects, required=False)
    participants = serializers.ListField(child=serializers.UUIDField(), required=False, allow_empty=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    allow_duplicate = serializers.BooleanField(required=False, default=False)

    def validate_participants(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("Jamaah yang sama tidak boleh dua kali dalam satu booking.")
        return value


class BookingTransitionSerializer(serializers.Serializer):
    """POST /bookings/{id}/transition — target wajib; alasan wajib saat cancel."""

    target = serializers.ChoiceField(choices=BookingStatus.choices)
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=1000)
