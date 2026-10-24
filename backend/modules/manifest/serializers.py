"""Serializer manifest & checklist dokumen (Spec §5.2, §8.3, UI-11/UI-12)."""
from rest_framework import serializers

from modules.catalog.models import TravelPackage
from modules.manifest.models import DocumentRequirementDeadline
from modules.pilgrims.models import PilgrimDocumentKind


def requirement_payload(row) -> dict:
    return {
        "id": str(row.id),
        "environment": row.environment,
        "package_id": str(row.package_id) if row.package_id else None,
        "package_code": row.package.code if row.package_id else None,
        "kind": row.kind,
        "mandatory": row.mandatory,
        "deadline_rule": row.deadline_rule,
    }


def version_payload(row) -> dict:
    return {
        "id": str(row.id),
        "version_no": row.version_no,
        "published_by_name": (
            (row.published_by.full_name or row.published_by.email)
            if row.published_by_id
            else None
        ),
        "checksum": row.checksum,
        "snapshot_object_key": row.snapshot_object_key,
        "created_at": row.created_at.isoformat(),
    }


def manifest_payload(*, departure, rows, versions, requirements) -> dict:
    """Envelope manifest (UI-12): metadata keberangkatan + roster + versi + checklist."""
    dep = departure
    return {
        "departure": {
            "id": str(dep.pk),
            "code": dep.code,
            "package_id": str(dep.package_id),
            "package_code": dep.package.code,
            "package_name": dep.package.name,
            "start_at": dep.start_at.isoformat(),
            "city_of_origin": dep.city_of_origin,
            "route": dep.route,
            "status": dep.status,
            "seat_capacity": dep.seat_capacity,
            "seats_taken": dep.seats_taken,
            "available_seats": dep.available_seats,
        },
        "rows": rows,
        "row_count": len(rows),
        "versions": [version_payload(v) for v in versions],
        "requirements": [requirement_payload(r) for r in requirements],
    }


class DocumentRequirementSerializer(serializers.Serializer):
    """Create/update syarat dokumen (UI-11 checklist, MOD-08).

    `package` kosong = checklist global; ada = menimpa global per `kind`.
    """

    package = serializers.PrimaryKeyRelatedField(
        queryset=TravelPackage.objects, required=False, allow_null=True
    )
    kind = serializers.ChoiceField(choices=PilgrimDocumentKind.choices)
    mandatory = serializers.BooleanField(required=False, default=True)
    deadline_rule = serializers.ChoiceField(
        choices=DocumentRequirementDeadline.choices, required=False,
        default=DocumentRequirementDeadline.BEFORE_READY,
    )
