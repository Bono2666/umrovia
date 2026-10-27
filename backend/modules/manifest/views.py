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
import hashlib
import json
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.storage import default_storage
from django.db import IntegrityError
from django.http import HttpResponse
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.booking.models import ParticipantStatus, SaasChargeState
from modules.departures.models import Departure
from modules.manifest import printing
from modules.manifest.models import DocumentRequirement, ManifestVersion
from modules.manifest.serializers import (
    DocumentRequirementSerializer,
    manifest_payload,
    requirement_payload,
    version_payload,
)
from modules.manifest.services import (
    PAYMENT_FILTERS,
    active_participants,
    checklist_gaps,
    effective_requirements,
    export_csv,
    export_filename,
    manifest_rows,
    publish_manifest,
    readiness,
)
from modules.payments.services import issuer_snapshot
from modules.pilgrims.crypto import PIIDecryptionError, decrypt_pii
from modules.tenants.branches import has_full_scope, require_full_scope
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
    payment = (params.get("payment") or "").strip()
    if payment not in PAYMENT_FILTERS:
        raise ValidationError({"payment": "Filter pembayaran harus paid, partial atau unpaid."})
    booking = (params.get("booking") or "").strip()
    if booking:
        try:
            booking = str(UUID(booking))
        except ValueError:
            raise ValidationError({"booking": "ID booking tidak valid."}) from None
    return {
        "q": (params.get("q") or "").strip(),
        "document": document,
        "participant_status": participant_status,
        "charge_state": charge_state,
        "payment": payment,
        "booking": booking,
    }


def _flag(params, name):
    return (params.get(name) or "").strip().lower() in ("1", "true", "yes")


def _departure_meta(dep) -> dict:
    return {
        "id": str(dep.pk), "code": dep.code, "package_code": dep.package.code, "package_name": dep.package.name,
        "start_at": dep.start_at.isoformat(), "end_at": dep.end_at.isoformat() if dep.end_at else None,
        "city_of_origin": dep.city_of_origin, "route": dep.route, "meeting_point": dep.meeting_point,
    }


def _require_pii(request, dep, *, action, changes):
    """OPS-03: data pribadi lengkap hanya `manifest.export_pii`; penolakan diaudit."""
    if has_permission(permission_list(request.membership.role), "manifest.export_pii"):
        return
    log_event(action=action, request=request, object_type="departure", object_id=str(dep.pk), changes={"pii": True, **changes})
    raise PermissionDenied("Data pribadi lengkap memerlukan permission 'manifest.export_pii'.")


def _file_response(data, content_type, filename):
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


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
        rows = _scoped_rows(request, dep, manifest_rows(dep, pii=False, **filters))
        versions = list(ManifestVersion.objects.filter(departure=dep)[:20])
        payload = manifest_payload(
            departure=dep,
            rows=rows,
            versions=versions,
            requirements=effective_requirements(dep.package),
        )
        if (request.query_params.get("checklist_gaps") or "").strip() in ("1", "true", "yes"):
            payload["checklist_gaps"] = checklist_gaps(dep, stage="before_ready")
        # Ringkasan kesiapan selalu atas seluruh roster, bukan hasil filter.
        payload["readiness"] = readiness(dep, None if any(filters.values()) or not has_full_scope(request) else rows)
        payload["full_scope"] = has_full_scope(request)
        return Response(payload)


class ManifestPublishView(APIView):
    """POST /departures/{id}/manifest/publish — snapshot versi (§7.6, OPS-04)."""

    permission_classes = [IsAuthenticated, require_permission("manifest.publish")]

    def post(self, request, departure_id):
        require_full_scope(request, "Penerbitan manifest resmi")
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

        if pii:
            _require_pii(request, dep, action="manifest.export_denied", changes={"filters": filters})

        kind = (request.query_params.get("file") or "csv").strip().lower()
        if kind not in {"csv", "xlsx", "pdf"}:
            raise ValidationError({"file": "Pilih csv, xlsx atau pdf."})
        name = export_filename(dep).rsplit(".", 1)[0]
        if kind == "csv":
            body, row_count = export_csv(dep, pii=pii, **filters)
            response = _file_response(body, "text/csv; charset=utf-8", f"{name}.csv")
        else:
            rows = _scoped_rows(request, dep, manifest_rows(dep, pii=pii, **filters))
            row_count = len(rows)
            meta = printing.print_meta(title="Manifest jamaah", travel=request.tenant.display_name, environment=dep.environment, actor=request.user, zone=request.tenant.timezone)
            if kind == "xlsx":
                response = _file_response(printing.manifest_xlsx(departure=_departure_meta(dep), rows=rows, pii=pii, meta=meta), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"{name}.xlsx")
            else:
                response = _file_response(printing.manifest_pdf(departure=_departure_meta(dep), rows=rows, pii=pii, meta=meta), "application/pdf", f"{name}.pdf")
        log_event(
            action="manifest.exported",
            request=request,
            object_type="departure",
            object_id=str(dep.pk),
            changes={"format": kind, "pii": pii, "rows": row_count, "filters": filters},
        )
        return response


class ManifestVersionPdfView(APIView):
    """GET /departures/{id}/manifest/versions/{n}/pdf — cetak versi terbit dari
    snapshot beku (OPS-04: versi, waktu, penerbit). Checksum diverifikasi."""

    permission_classes = [IsAuthenticated, require_permission("manifest.export")]

    def get(self, request, departure_id, version_no):
        require_full_scope(request, "Manifest resmi")
        dep = _get_departure(departure_id)
        version = ManifestVersion.objects.filter(departure=dep, version_no=version_no).select_related("published_by").first()
        if version is None:
            raise NotFound("Versi manifest tidak ditemukan.")
        with default_storage.open(version.snapshot_object_key, "rb") as handle:
            raw = handle.read()
        if hashlib.sha256(raw).hexdigest() != version.checksum:
            raise ValidationError({"version": "Checksum snapshot tidak cocok; versi tidak dapat dicetak."})
        snapshot = json.loads(raw)
        meta = printing.print_meta(title=f"Manifest v{version_no}", travel=request.tenant.display_name, environment=dep.environment, actor=request.user, zone=request.tenant.timezone)
        published = {
            "version_no": version_no,
            "published_at": printing.document_date(snapshot["published_at"], request.tenant.timezone, with_time=True),
            "published_by": (version.published_by.full_name or version.published_by.email) if version.published_by_id else "sistem",
        }
        departure = {**_departure_meta(dep), **{k: v for k, v in snapshot["departure"].items() if k in {"code", "package_name", "start_at", "city_of_origin", "route"}}}
        pdf = printing.manifest_pdf(departure=departure, rows=snapshot["rows"], pii=False, meta=meta, version=published)
        log_event(action="manifest.version_printed", request=request, object_type="departure", object_id=str(dep.pk), changes={"version_no": version_no})
        prefix = "DEMO-manifest" if dep.environment == "demo" else "manifest"
        return _file_response(pdf, "application/pdf", f"{prefix}-{dep.code}-v{version_no}.pdf")


PRINT_KINDS = {"registration-forms": "Formulir pendaftaran", "labels": "Label jamaah", "envelopes": "Amplop jamaah"}


def _allowed_bookings(request, dep):
    """TBD-08 opsi C: booking keberangkatan dalam cakupan cabang staf (None = semua)."""
    from modules.booking.models import Booking
    from modules.tenants.branches import branch_scope, scope_filter

    if branch_scope(request) is None:
        return None
    return {str(pk) for pk in scope_filter(Booking.objects.filter(departure=dep), request).values_list("pk", flat=True)}


def _scoped_rows(request, dep, rows):
    allowed = _allowed_bookings(request, dep)
    return rows if allowed is None else [row for row in rows if row["booking_id"] in allowed]


def _people(dep, *, booking="", pii=False, allowed=None):
    people = []
    for row in active_participants(dep):
        if booking and str(row.booking_id) != booking:
            continue
        if allowed is not None and str(row.booking_id) not in allowed:
            continue
        p = row.pilgrim
        person = {
            "code": p.code, "name": p.name, "gender": p.gender, "birth_place": p.birth_place,
            "birth_date": p.birth_date.isoformat() if p.birth_date else None,
            "passport_expires_at": p.passport_expires_at.isoformat() if p.passport_expires_at else None,
            "identity_masked": p.identity_masked, "passport_masked": p.passport_masked,
            "address": p.address, "phone": p.phone, "email": p.email,
            "guardian_name": p.guardian_name, "guardian_relation": p.guardian_relation,
            "emergency_contact_name": p.emergency_contact_name, "emergency_contact_phone": p.emergency_contact_phone,
            "booking_code": row.booking.code, "room_type": row.pricing_snapshot_json.get("room_type") or "",
        }
        if pii:
            try:
                person["identity_number"] = decrypt_pii(p.identity_encrypted)
                person["passport_number"] = decrypt_pii(p.passport_encrypted)
            except PIIDecryptionError as exc:
                raise ValidationError({"pii": "Dekripsi data pribadi gagal; periksa kunci enkripsi."}) from exc
        people.append(person)
    return people


class DeparturePrintView(APIView):
    """GET /departures/{id}/print/{kind} — formulir pendaftaran, label koper,
    amplop (PRD MOD-12). `?booking=` membatasi satu booking; `?pii=1` (hanya
    formulir) menampilkan NIK/paspor lengkap dengan izin `manifest.export_pii`."""

    permission_classes = [IsAuthenticated, require_permission("manifest.export")]

    def get(self, request, departure_id, kind):
        if kind not in PRINT_KINDS:
            raise NotFound("Jenis dokumen cetak tidak dikenal.")
        dep = _get_departure(departure_id)
        booking = _filters({"booking": request.query_params.get("booking", "")})["booking"]
        pii = kind == "registration-forms" and _flag(request.query_params, "pii")
        if pii:
            _require_pii(request, dep, action="manifest.print_denied", changes={"kind": kind})
        people = _people(dep, booking=booking, pii=pii, allowed=_allowed_bookings(request, dep))
        meta = printing.print_meta(title=PRINT_KINDS[kind], travel=request.tenant.display_name, environment=dep.environment, actor=request.user, zone=request.tenant.timezone)
        departure = _departure_meta(dep)
        if kind == "registration-forms":
            pdf = printing.registration_forms_pdf(departure=departure, people=people, pii=pii, meta=meta, issuer=issuer_snapshot(request.tenant))
        elif kind == "labels":
            pdf = printing.labels_pdf(departure=departure, people=people, meta=meta)
        else:
            pdf = printing.envelopes_pdf(people=people, meta=meta, issuer=issuer_snapshot(request.tenant))
        log_event(action="manifest.printed", request=request, object_type="departure", object_id=str(dep.pk), changes={"kind": kind, "pii": pii, "rows": len(people), "booking": booking})
        prefix = "DEMO-" if dep.environment == "demo" else ""
        return _file_response(pdf, "application/pdf", f"{prefix}{kind}-{dep.code}.pdf")


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
