"""Serializer keberangkatan (Spec §8.3, UI-05) + transisi status."""
from rest_framework import serializers

from modules.departures.models import Departure, DepartureStatus
from modules.tenants.models import MembershipStatus, TenantMembership


def departure_payload(dep: Departure) -> dict:
    from modules.booking.models import Booking

    has_bookings = dep.has_bookings if hasattr(dep, "has_bookings") else Booking.objects.filter(departure=dep).exists()
    return {
        "has_bookings": has_bookings,
        # Perkiraan untuk UI; DELETE juga memeriksa riwayat status dan manifest.
        "deletable": dep.status == "DRAFT" and not has_bookings,
        "id": str(dep.id),
        "environment": dep.environment,
        "code": dep.code,
        "package_id": str(dep.package_id),
        "package_code": dep.package.code,
        "package_name": dep.package.name,
        "package_price_idr": dep.package.price_idr,
        "room_prices": [{"room_type": r.room_type, "price_idr": r.price_idr} for r in dep.package.room_prices.all()],
        "start_at": dep.start_at.isoformat(),
        "end_at": dep.end_at.isoformat() if dep.end_at else None,
        "city_of_origin": dep.city_of_origin,
        "route": dep.route,
        "meeting_point": dep.meeting_point,
        "seat_capacity": dep.seat_capacity,
        "seats_blocked": dep.seats_blocked,
        "seats_taken": dep.seats_taken,
        "available_seats": dep.available_seats,
        "registration_deadline": (
            dep.registration_deadline.isoformat() if dep.registration_deadline else None
        ),
        "lead_staff": str(dep.lead_staff_id) if dep.lead_staff_id else None,
        "lead_staff_name": (
            (dep.lead_staff.full_name or dep.lead_staff.email) if dep.lead_staff_id else None
        ),
        "status": dep.status,
        "notes": dep.notes,
    }


class DepartureWriteSerializer(serializers.ModelSerializer):
    """Create/update keberangkatan. `seats_taken` TIDAK writable (hanya via
    layanan seat atomik); `seat_capacity`/`seats_blocked` ber-guard agar
    invariant BR-002 tidak pernah dilanggar di level aplikasi."""

    # `package` dibiarkan digenerate ModelSerializer (queryset = Manager,
    # dievaluasi saat validasi dengan context tenant aktif → paket tenant
    # lain ditolak 400, bukan lolos siluman).

    class Meta:
        model = Departure
        fields = [
            "package", "start_at", "end_at", "city_of_origin", "route",
            "meeting_point", "seat_capacity", "seats_blocked",
            "registration_deadline", "lead_staff", "notes",
        ]

    def validate_city_of_origin(self, value):
        if not value.strip():
            raise serializers.ValidationError("Kota asal wajib diisi.")
        return value.strip()

    def validate_lead_staff(self, value):
        if value is not None and not TenantMembership.objects.filter(
            user=value, status=MembershipStatus.ACTIVE, user__status="ACTIVE"
        ).exists():
            raise serializers.ValidationError("PIC harus staf aktif pada workspace ini.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        start = attrs.get("start_at", getattr(self.instance, "start_at", None))
        end = attrs.get("end_at", getattr(self.instance, "end_at", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"end_at": "Kepulangan harus setelah keberangkatan (§10.1)."})
        deadline = attrs.get(
            "registration_deadline", getattr(self.instance, "registration_deadline", None)
        )
        if deadline and start and deadline > start.date():
            raise serializers.ValidationError(
                {"registration_deadline": "Batas pendaftaran tidak boleh setelah tanggal keberangkatan."}
            )

        capacity = attrs.get("seat_capacity", getattr(self.instance, "seat_capacity", 0) or 0)
        blocked = attrs.get("seats_blocked", getattr(self.instance, "seats_blocked", 0) or 0)
        taken = getattr(self.instance, "seats_taken", 0) or 0
        if blocked + taken > capacity:
            raise serializers.ValidationError(
                {"seats_blocked": "Kuota blokir + kursi terpakai melebihi kapasitas (BR-002)."}
            )
        return attrs


class DepartureTransitionSerializer(serializers.Serializer):
    """POST /departures/{id}/transition — target wajib; alasan wajib saat cancel.

    `checklist_exception` (§6.5 *approved exception*, OPS02): izin melewati
    gerbang READY saat dokumen wajib belum lengkap — wajib menyertai `reason`
    dan tercatat di `departure_events` + audit.
    """

    target = serializers.ChoiceField(choices=DepartureStatus.choices)
    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=1000)
    checklist_exception = serializers.BooleanField(required=False, default=False)
