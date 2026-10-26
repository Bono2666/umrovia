"""Serializer paket (Spec §8.3 GET/POST /packages; UI-04)."""
from rest_framework import serializers

from modules.catalog.models import RoomType, TravelPackage


def package_payload(pkg: TravelPackage) -> dict:
    return {
        "id": str(pkg.id),
        "environment": pkg.environment,
        "code": pkg.code,
        "name": pkg.name,
        "kind": pkg.kind,
        "description": pkg.description,
        "duration_days": pkg.duration_days,
        "price_idr": pkg.price_idr,
        "room_prices": [{"room_type": r.room_type, "price_idr": r.price_idr} for r in pkg.room_prices.all()],
        "inclusions": pkg.inclusions_json,
        "exclusions": pkg.exclusions_json,
        "cancellation_policy": pkg.cancellation_policy,
        "payment_terms": pkg.payment_terms,
        "status": pkg.status,
        "published": pkg.published,
        "deletable": not (pkg.has_departures if hasattr(pkg, "has_departures") else pkg.departures.exists()),
    }


class RoomPriceSerializer(serializers.Serializer):
    room_type = serializers.ChoiceField(choices=RoomType.choices)
    price_idr = serializers.IntegerField(min_value=0, max_value=10_000_000_000)


class PackageWriteSerializer(serializers.ModelSerializer):
    """Create/update paket. `inclusions`/`exclusions` = daftar string (MOD-05)."""

    # `source` → menulis ke kolom model `*_json`; nama API tetap tanpa suffix.
    room_prices = RoomPriceSerializer(many=True, required=False)
    inclusions = serializers.ListField(
        source="inclusions_json",
        child=serializers.CharField(max_length=200),
        required=False,
        default=list,
    )
    exclusions = serializers.ListField(
        source="exclusions_json",
        child=serializers.CharField(max_length=200),
        required=False,
        default=list,
    )

    class Meta:
        model = TravelPackage
        fields = [
            "name", "kind", "description", "duration_days", "price_idr",
            "inclusions", "exclusions", "cancellation_policy", "payment_terms",
            "status", "published", "room_prices",
        ]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Nama paket wajib diisi.")
        return value.strip()

    def validate_room_prices(self, value):
        kinds = [row["room_type"] for row in value]
        if len(kinds) != len(set(kinds)):
            raise serializers.ValidationError("Tipe kamar tidak boleh berulang.")
        return value

    def validate_duration_days(self, value):
        if value > 365:
            raise serializers.ValidationError("Durasi maksimal 365 hari.")
        return value

    def validate_price_idr(self, value):
        # §10.1 amount nonnegatif & terbatas (ModelForm PositiveIntegerField
        # sudah nonnegatif; batas atas 10 miliar rupiah per paket).
        if value > 10_000_000_000:
            raise serializers.ValidationError("Harga dasar melebihi batas wajar (Rp10 miliar).")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        status_value = attrs.get("status", getattr(self.instance, "status", None))
        if attrs.get("published") and status_value != "ACTIVE":
            raise serializers.ValidationError(
                {"published": "Paket hanya boleh dipublikasikan saat status Aktif."}
            )
        return attrs
