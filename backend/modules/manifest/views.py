"""Manifest & checklist dokumen — Spec §8.3 (`GET /departures/{id}/manifest`,
`POST /departures/{id}/manifest/publish`; ekspor CSV dasar = exit gate S10),
§7.6 (snapshot versi + PII berizin & diaudit), UI-11/UI-12;
PRD MOD-08 (checklist), MOD-12 (filter), OPS-02 (gerbang READY — ditangani
di `departures.services` lewat `checklist_exception`), OPS-03 (ekspor PII
tanpa izin → ditolak DAN diaudit), UAT-14 (hanya peserta departure itu).

Pola mengikuti modul lain: permission `domain.object.action` via
`require_permission`, payload problem-detail `field_errors` untuk 400,
audit `log_event` per tindakan, guard environment writable untuk tulis.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.http import HttpResponse
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.booking.models import ParticipantStatus, SaasChargeState
from modules.departures.models import Departure
from modules.manifest.models import DocumentRequirement, ManifestVersion
from modules.manifest.serializers import (
    DocumentRequirementSerializer,
    manifest_payload,
    requirement_payload,
    version_payload,
)
from modules.manifest.services import (
    checklist_gaps,
    effective_requirements,
    export_csv,
    export_filename,
    manifest_rows,
    publish_manifest,
)
from modules.tenants.environment import (
    assert_environment_writable,
    resolve_active_environment,
)
from modules.tenants.rbac import has_permission, permission_list, require_permission

# Filter MOD-12 yang diizinkan pada roster manifest.
_DOCUMENT_FILTERS = {"", "complete", "incomplete"}
_PARTICIPANT_STATUSES = {c for c, _ in ParticipantStatus.choices}
_CHARGE_STATES = {c for c, _ in SaasChargeState.choices}


def _get_departure(departure_id) -> Departure:
    try:
        return Departure.objects.select_related("package").get(pk=departure_id)
    except (Departure.DoesNotExist, DjangoValidationError, ValueError):
        raise NotFound("Keberangkatan tidak ditemukan.") from None


def _filters(params) -> dict:
    """Parse filter MOD-12 → dict argumen `manifest_rows` (invalid → 400)."""
    document = (params.get("document") or "").strip()
    if document not in _DOCUMENT_FILTERS:
        raise ValidationError({"document": "Filter document harus complete atau incomplete."})
    participant_status = (params.get("participant_status") or "").strip()
    if participant_status and participant_status not in _PARTICIPANT_STATUSES:
        raise ValidationError({"participant_status": "Status peserta tidak dikenal."})
    charge_state = (params.get("charge_state") or "").strip()
    if charge_state and charge_state not in _CHARGE_STATES:
        raise ValidationError({"charge_state": "Status charge tidak dikenal."})
    return {
        "q": (params.get("q") or "").strip(),
        "document": document,
        "participant_status": participant_status,
        "charge_state": charge_state,
    }


class ManifestView(APIView):
    """GET /departures/{id}/manifest — roster (UI-12) + versi + checklist (UI-11).

    Selalu masked (§10.1); nilai PII penuh hanya lewat ekspor `pii=1` yang
    diaudit. `?checklist_gaps=1` memberi daftar kekurangan gerbang READY
    (OPD-01 tampilan, tanpa memutar balik transisi).
    """

    permission_classes = [IsAuthenticated, require_permission("manifest.read")]

    def get(self, request, departure_id):
        dep = _get_departure(departure_id)
        filters = _filters(request.query_params)
        rows = manifest_rows(dep, pii=False, **filters)
        versions = list(ManifestVersion.objects.filter(departure=dep)[:20])
        payload = manifest_payload(
            departure=dep,
            rows=rows,
            versions=versions,
            requirements=effective_requirements(dep.package),
        )
        if (request.query_params.get("checklist_gaps") or "").strip() in ("1", "true", "yes"):
            payload["checklist_gaps"] = checklist_gaps(dep, stage="before_ready")
        return Response(payload)


class ManifestPublishView(APIView):
    """POST /departures/{id}/manifest/publish — snapshot versi (§7.6, OPS-04)."""

    permission_classes = [IsAuthenticated, require_permission("manifest.publish")]

    def post(self, request, departure_id):
        dep = _get_departure(departure_id)
        assert_environment_writable(request.tenant, dep.environment)
        version = publish_manifest(departure=dep, actor=request.user)
        log_event(
            action="manifest.published",
            request=request,
            object_type="departure",
            object_id=str(dep.pk),
            changes={"version_no": version.version_no, "checksum": version.checksum},
        )
        return Response({"version": version_payload(version)}, status=201)


class ManifestExportView(APIView):
    """GET /departures/{id}/manifest/export — CSV (exit gate S10).

    `?pii=1` menuntut grant `manifest.export_pii` (matriks §3: Owner saja di
    v1); tanpa izin → 403 DAN audit `manifest.export_denied` (OPS-03).
    Ekspor terautorisasi tercatat `manifest.exported` berisi flag PII + jumlah
    baris + filter (UAT-14 terpenuhi by construction: selalu dibatasi satu
    departure lewat URL).
    """

    permission_classes = [IsAuthenticated, require_permission("manifest.export")]

    def get(self, request, departure_id):
        dep = _get_departure(departure_id)
        filters = _filters(request.query_params)
        pii = (request.query_params.get("pii") or "").strip().lower() in ("1", "true", "yes")

        if pii and not has_permission(
            permission_list(request.membership.role), "manifest.export_pii"
        ):
            log_event(
                action="manifest.export_denied",
                request=request,
                object_type="departure",
                object_id=str(dep.pk),
                changes={"pii": True, "filters": filters},
            )
            raise PermissionDenied(
                "Ekspor manifest dengan PII memerlukan permission 'manifest.export_pii'."
            )

        csv_text, row_count = export_csv(dep, pii=pii, **filters)
        log_event(
            action="manifest.exported",
            request=request,
            object_type="departure",
            object_id=str(dep.pk),
            changes={"format": "csv", "pii": pii, "rows": row_count, "filters": filters},
        )
        response = HttpResponse(csv_text, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{export_filename(dep)}"'
        return response


class DocumentRequirementListCreateView(APIView):
    """GET/POST /document-requirements — definisi checklist operasional (UI-11)."""

    permission_classes = [
        IsAuthenticated,
        require_permission("documents.requirements.manage"),
    ]

    def get(self, request):
        environment = resolve_active_environment(request.tenant)
        rows = DocumentRequirement.objects.filter(environment=environment).order_by(
            "package__code", "kind"
        )
        return Response([requirement_payload(r) for r in rows])

    def post(self, request):
        environment = resolve_active_environment(request.tenant)
        assert_environment_writable(request.tenant, environment)
        serializer = DocumentRequirementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        package = data.get("package")
        if package is not None and package.environment != environment:
            raise ValidationError(
                {"package": f"Paket harus berasal dari environment {environment}."}
            )
        try:
            row = DocumentRequirement.objects.create(
                tenant=request.tenant,
                environment=environment,
                package=package,
                kind=data["kind"],
                mandatory=data["mandatory"],
                deadline_rule=data["deadline_rule"],
            )
        except IntegrityError:
            raise ValidationError(
                {"kind": "Syarat dokumen untuk jenis ini sudah ada pada lingkup tersebut."}
            ) from None
        log_event(
            action="document_requirements.created",
            request=request,
            object_type="document_requirement",
            object_id=str(row.id),
            changes={"kind": row.kind, "package_id": str(row.package_id or "")},
        )
        return Response(requirement_payload(row), status=201)


class DocumentRequirementDetailView(APIView):
    """GET/PATCH/DELETE /document-requirements/{id} — ubah checklist (UI-11)."""

    permission_classes = [
        IsAuthenticated,
        require_permission("documents.requirements.manage"),
    ]

    def _row(self, requirement_id) -> DocumentRequirement:
        try:
            return DocumentRequirement.objects.get(pk=requirement_id)
        except (DocumentRequirement.DoesNotExist, DjangoValidationError, ValueError):
            raise NotFound("Syarat dokumen tidak ditemukan.") from None

    def get(self, request, requirement_id):
        return Response(requirement_payload(self._row(requirement_id)))

    def patch(self, request, requirement_id):
        row = self._row(requirement_id)
        assert_environment_writable(request.tenant, row.environment)
        serializer = DocumentRequirementSerializer(row, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        package = data.get("package", row.package)
        if package is not None and package.environment != row.environment:
            raise ValidationError(
                {"package": f"Paket harus berasal dari environment {row.environment}."}
            )
        if "package" in data:
            row.package = package
        if "kind" in data:
            row.kind = data["kind"]
        if "mandatory" in data:
            row.mandatory = data["mandatory"]
        if "deadline_rule" in data:
            row.deadline_rule = data["deadline_rule"]
        try:
            row.full_clean()
            row.save()
        except IntegrityError:
            raise ValidationError(
                {"kind": "Syarat dokumen untuk jenis ini sudah ada pada lingkup tersebut."}
            ) from None
        except DjangoValidationError as exc:
            raise ValidationError(
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            ) from exc
        log_event(
            action="document_requirements.updated",
            request=request,
            object_type="document_requirement",
            object_id=str(row.id),
            changes={"kind": row.kind, "mandatory": row.mandatory},
        )
        return Response(requirement_payload(row))

    def delete(self, request, requirement_id):
        row = self._row(requirement_id)
        assert_environment_writable(request.tenant, row.environment)
        log_event(
            action="document_requirements.deleted",
            request=request,
            object_type="document_requirement",
            object_id=str(row.id),
            changes={"kind": row.kind, "package_id": str(row.package_id or "")},
        )
        row.delete()
        return Response(status=204)
