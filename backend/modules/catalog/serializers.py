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
        "child_no_bed_price_idr": pkg.child_no_bed_price_idr,
        "infant_price_idr": pkg.infant_price_idr,
        "addons": pkg.addons_json,
        "estimated_costs": pkg.estimated_costs_json,
        "estimated_cost_per_pax_idr": sum(int(row.get("amount_idr") or 0) for row in pkg.estimated_costs_json),
        "estimated_margin_per_pax_idr": pkg.price_idr - sum(int(row.get("amount_idr") or 0) for row in pkg.estimated_costs_json),
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


class AddonSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^[A-Za-z0-9_-]{2,24}$", error_messages={"invalid": "Kode 2–24 huruf/angka."})
    name = serializers.CharField(max_length=120)
    price_idr = serializers.IntegerField(min_value=0, max_value=1_000_000_000)


class CostItemSerializer(serializers.Serializer):
    category = serializers.CharField(max_length=40)
    description = serializers.CharField(max_length=160)
    amount_idr = serializers.IntegerField(min_value=0, max_value=1_000_000_000)


class PackageWriteSerializer(serializers.ModelSerializer):
    """Create/update paket. `inclusions`/`exclusions` = daftar string (MOD-05)."""

    # `source` → menulis ke kolom model `*_json`; nama API tetap tanpa suffix.
    room_prices = RoomPriceSerializer(many=True, required=False)
    addons = AddonSerializer(many=True, source="addons_json", required=False)
    estimated_costs = CostItemSerializer(many=True, source="estimated_costs_json", required=False)
    child_no_bed_price_idr = serializers.IntegerField(min_value=0, max_value=10_000_000_000, required=False, allow_null=True)
    infant_price_idr = serializers.IntegerField(min_value=0, max_value=10_000_000_000, required=False, allow_null=True)
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
            "status", "published", "room_prices", "child_no_bed_price_idr", "infant_price_idr", "addons", "estimated_costs",
        ]

    def validate_addons(self, value):
        codes = [row["code"].upper() for row in value]
        if len(codes) != len(set(codes)):
            raise serializers.ValidationError("Kode layanan tambahan tidak boleh berulang.")
        return [{**row, "code": row["code"].upper(), "name": row["name"].strip()} for row in value]

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
