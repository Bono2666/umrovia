"""Serializer jamaah + dokumen (Spec §8.3, §10.1).

Field sensitif (`identity_number`, `passport_number`) bersifat write-only —
nilai asli tidak pernah masuk payload respons; output selalu varian masked.
"""
from datetime import date

from rest_framework import serializers

from modules.pilgrims.crypto import (
    normalize_digits,
    normalize_passport,
    normalize_phone,
)
from modules.pilgrims.models import Pilgrim, PilgrimDocument, PilgrimDocumentKind


def pilgrim_payload(pilgrim: Pilgrim, *, include_restricted: bool = True) -> dict:
    """Payload API jamaah — HANYA masked, tanpa nilai PII mentah (§10.1).

    `special_needs` (catatan kebutuhan khusus, akses terbatas MOD-04) hanya
    ikut bila diminta (detail), tidak di daftar.
    """
    if hasattr(pilgrim, "in_booking"):
        used = pilgrim.in_booking or pilgrim.has_documents
    else:
        used = pilgrim.booking_participations.exists() or pilgrim.documents.exists()
    data = {
        "deletable": not used,  # jamaah terpakai diarsipkan, tidak dihapus
        "id": str(pilgrim.id),
        "code": pilgrim.code,
        "environment": pilgrim.environment,
        "name": pilgrim.name,
        "gender": pilgrim.gender,
        "birth_date": pilgrim.birth_date.isoformat() if pilgrim.birth_date else None,
        "birth_place": pilgrim.birth_place,
        "nationality": pilgrim.nationality,
        "marital_status": pilgrim.marital_status,
        "address": pilgrim.address,
        "email": pilgrim.email,
        "phone": pilgrim.phone,
        "emergency_contact_name": pilgrim.emergency_contact_name,
        "emergency_contact_phone": pilgrim.emergency_contact_phone,
        "guardian_name": pilgrim.guardian_name,
        "guardian_relation": pilgrim.guardian_relation,
        "identity_masked": pilgrim.identity_masked,
        "passport_masked": pilgrim.passport_masked,
        "passport_name": pilgrim.passport_name,
        "passport_issued_at": pilgrim.passport_issued_at.isoformat() if pilgrim.passport_issued_at else None,
        "passport_expires_at": pilgrim.passport_expires_at.isoformat() if pilgrim.passport_expires_at else None,
        "passport_place_of_issue": pilgrim.passport_place_of_issue,
        "status": pilgrim.status,
        "possible_duplicate_of": str(pilgrim.possible_duplicate_of_id) if pilgrim.possible_duplicate_of_id else None,
    }
    if include_restricted:
        data["special_needs"] = pilgrim.special_needs
    return data


class PilgrimWriteSerializer(serializers.ModelSerializer):
    """Create/update jamaah: NIK & paspor write-only, ternormalisasi + terenkripsi."""

    identity_number = serializers.CharField(required=False, allow_blank=True, write_only=True)
    passport_number = serializers.CharField(required=False, allow_blank=True, write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True, max_length=32)
    emergency_contact_phone = serializers.CharField(required=False, allow_blank=True, max_length=32)

    class Meta:
        model = Pilgrim
        fields = [
            "name", "gender", "birth_date", "birth_place", "nationality", "marital_status",
            "address", "email", "phone", "emergency_contact_name", "emergency_contact_phone",
            "guardian_name", "guardian_relation", "special_needs",
            "identity_number", "passport_number", "passport_name", "passport_issued_at",
            "passport_expires_at", "passport_place_of_issue", "status",
        ]
        extra_kwargs = {
            "name": {"max_length": 160},
            "passport_name": {"required": False, "allow_blank": True, "max_length": 160},
        }

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Nama sesuai dokumen wajib diisi.")
        return value.strip()

    def validate_identity_number(self, value):
        digits = normalize_digits(value)
        if digits and len(digits) != 16:
            raise serializers.ValidationError("NIK harus 16 digit.")
        return digits

    def validate_passport_number(self, value):
        normalized = normalize_passport(value)
        if normalized and not (5 <= len(normalized) <= 12):
            raise serializers.ValidationError("Nomor paspor tidak valid (5–12 karakter alfanumerik).")
        return normalized

    def validate(self, attrs):
        attrs = super().validate(attrs)
        phone = attrs.get("phone")
        if phone:
            attrs["phone"] = normalize_phone(phone)
        ephone = attrs.get("emergency_contact_phone")
        if ephone:
            attrs["emergency_contact_phone"] = normalize_phone(ephone)
        birth = attrs.get("birth_date")
        if birth and birth > date.today():
            raise serializers.ValidationError({"birth_date": "Tanggal lahir tidak boleh di masa depan."})
        expires = attrs.get("passport_expires_at", getattr(self.instance, "passport_expires_at", None))
        issued = attrs.get("passport_issued_at", getattr(self.instance, "passport_issued_at", None))
        if expires and issued and expires < issued:
            raise serializers.ValidationError({"passport_expires_at": "Tanggal kedaluwarsa sebelum terbit."})
        return attrs


class PilgrimDocumentRegisterSerializer(serializers.ModelSerializer):
    """Registrasi metadata dokumen: object_key wajib ber-prefix tenant/environment (§5.2)."""

    kind = serializers.ChoiceField(choices=PilgrimDocumentKind.choices)

    class Meta:
        model = PilgrimDocument
        fields = ["kind", "object_key"]

    def validate_object_key(self, value):
        pilgrim = self.context["pilgrim"]
        expected = f"tenants/{pilgrim.tenant_id}/environments/{pilgrim.environment}/pilgrims/{pilgrim.id}/"
        if not value.startswith(expected):
            raise serializers.ValidationError(f"object_key harus diawali '{expected}'.")
        if ".." in value or value.endswith("/"):
            raise serializers.ValidationError("object_key tidak valid.")
        return value


class PilgrimDocumentReviewSerializer(serializers.ModelSerializer):
    """Review dokumen: approve/reject — `reason` wajib saat reject (UI-11)."""

    status = serializers.ChoiceField(choices=["APPROVED", "REJECTED"])

    class Meta:
        model = PilgrimDocument
        fields = ["status", "reason"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Object-level: `validate_reason` tidak terpanggil bila `reason` tidak
        # dikirim sama sekali — reject tanpa alasan wajib tetap tertangkap (UI-11).
        if "status" not in attrs:
            raise serializers.ValidationError({"status": "Status hasil review wajib diisi."})
        status_value = attrs["status"]
        reason = (attrs.get("reason") or "").strip()
        if status_value == "REJECTED" and not reason:
            raise serializers.ValidationError({"reason": "Alasan penolakan wajib diisi."})
        if "reason" in attrs:  # approve tanpa alasan → reason lama tidak dihapus
            attrs["reason"] = reason
        return attrs


def document_payload(doc: PilgrimDocument) -> dict:
    from modules.portal.files import has_file

    return {
        "id": str(doc.id),
        "pilgrim_id": str(doc.pilgrim_id),
        "environment": doc.environment,
        "kind": doc.kind,
        "object_key": doc.object_key,
        "version": doc.version,
        "status": doc.status,
        "reviewed_by": str(doc.reviewed_by_id) if doc.reviewed_by_id else None,
        "reviewed_at": doc.reviewed_at.isoformat() if doc.reviewed_at else None,
        "reason": doc.reason,
        "uploaded_at": doc.created_at.isoformat(),
        "has_file": has_file(doc),
    }


__all__ = [
    "PilgrimWriteSerializer",
    "PilgrimDocumentRegisterSerializer",
    "PilgrimDocumentReviewSerializer",
    "pilgrim_payload",
    "document_payload",
]
