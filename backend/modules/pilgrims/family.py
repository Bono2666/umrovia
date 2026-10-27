"""MOD-04 lanjutan: kelompok keluarga, riwayat jamaah, dan ekspor daftar jamaah terotorisasi.

Ekspor default memakai nilai termask; NIK/paspor lengkap hanya untuk
`reports.export_pii` (Owner) dan setiap ekspor dicatat di audit log.
"""
import csv
import io

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.pilgrims.crypto import decrypt_pii
from modules.pilgrims.models import FamilyGroup, Pilgrim
from modules.tenants.environment import assert_environment_writable, resolve_active_environment
from modules.tenants.rbac import has_permission, permission_list, require_permission

RELATIONS = ["Kepala keluarga", "Suami", "Istri", "Anak", "Orang tua", "Saudara", "Mahram", "Lainnya"]


def family_payload(group, members=None):
    members = list(group.members.order_by("name")) if members is None else members
    return {"id": str(group.pk), "name": group.name, "notes": group.notes,
            "members": [{"id": str(p.pk), "code": p.code, "name": p.name, "relation": p.family_relation, "gender": p.gender} for p in members]}


class FamilySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class FamilyListCreateView(APIView):
    def get_permissions(self):
        return [IsAuthenticated(), require_permission("pilgrims.write" if self.request.method == "POST" else "pilgrims.read")()]

    @extend_schema(operation_id="families_list", responses=OpenApiTypes.OBJECT, parameters=[OpenApiParameter("q", str)])
    def get(self, request):
        qs = FamilyGroup.objects.filter(environment=resolve_active_environment(request.tenant)).prefetch_related("members")
        q = (request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        return Response({"results": [family_payload(g, sorted(g.members.all(), key=lambda p: p.name)) for g in qs[:200]]})

    @extend_schema(request=FamilySerializer, responses={201: OpenApiTypes.OBJECT})
    @transaction.atomic
    def post(self, request):
        environment = resolve_active_environment(request.tenant)
        assert_environment_writable(request.tenant, environment)
        serializer = FamilySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        group = FamilyGroup.objects.create(tenant=request.tenant, environment=environment, name=serializer.validated_data["name"].strip(), notes=serializer.validated_data["notes"].strip())
        log_event(action="families.created", request=request, object_type="family", object_id=group.pk, changes={"name": group.name})
        return Response(family_payload(group, []), status=status.HTTP_201_CREATED)


class FamilyMemberView(APIView):
    """POST /families/{id}/members {pilgrim, relation} menambah/memindahkan; DELETE …?pilgrim= mengeluarkan."""

    permission_classes = [IsAuthenticated, require_permission("pilgrims.write")]

    def _group(self, request, family_id):
        group = FamilyGroup.objects.filter(pk=family_id, environment=resolve_active_environment(request.tenant)).first()
        if group is None:
            raise NotFound("Keluarga tidak ditemukan.")
        assert_environment_writable(request.tenant, group.environment)
        return group

    def _pilgrim(self, group, pilgrim_id):
        pilgrim = Pilgrim.objects.select_for_update().filter(pk=pilgrim_id, environment=group.environment).first() if pilgrim_id else None
        if pilgrim is None:
            raise ValidationError({"pilgrim": "Jamaah tidak ditemukan."})
        return pilgrim

    @transaction.atomic
    def post(self, request, family_id):
        group = self._group(request, family_id)
        pilgrim = self._pilgrim(group, request.data.get("pilgrim"))
        relation = str(request.data.get("relation") or "").strip()
        if relation not in RELATIONS:
            raise ValidationError({"relation": f"Pilih hubungan: {', '.join(RELATIONS)}."})
        if relation == "Kepala keluarga" and group.members.filter(family_relation="Kepala keluarga").exclude(pk=pilgrim.pk).exists():
            raise ValidationError({"relation": "Keluarga ini sudah memiliki kepala keluarga."})
        previous = pilgrim.family_id
        pilgrim.family, pilgrim.family_relation = group, relation
        pilgrim.save(update_fields=["family", "family_relation", "updated_at"])
        log_event(action="families.member_set", request=request, object_type="family", object_id=group.pk, changes={"pilgrim": pilgrim.code, "relation": relation, "moved_from": str(previous) if previous and previous != group.pk else None})
        return Response(family_payload(group))

    @transaction.atomic
    def delete(self, request, family_id):
        group = self._group(request, family_id)
        pilgrim = self._pilgrim(group, request.query_params.get("pilgrim"))
        if pilgrim.family_id != group.pk:
            raise ValidationError({"pilgrim": "Jamaah bukan anggota keluarga ini."})
        pilgrim.family, pilgrim.family_relation = None, ""
        pilgrim.save(update_fields=["family", "family_relation", "updated_at"])
        log_event(action="families.member_removed", request=request, object_type="family", object_id=group.pk, changes={"pilgrim": pilgrim.code})
        return Response(family_payload(group))


class PilgrimHistoryView(APIView):
    """GET /pilgrims/{id}/history — seluruh booking/keberangkatan, pembayaran, dokumen & permintaan koreksi."""

    permission_classes = [IsAuthenticated, require_permission("pilgrims.read")]

    def get(self, request, pilgrim_id):
        from django.db.models import Sum

        from modules.booking.models import BookingParticipant
        from modules.booking.services import participant_net
        from modules.payments.models import PaymentAllocation

        pilgrim = Pilgrim.objects.filter(pk=pilgrim_id).select_related("family").first()
        if pilgrim is None:
            raise NotFound("Jamaah tidak ditemukan.")
        participations = BookingParticipant.objects.filter(pilgrim=pilgrim).select_related("booking__departure__package").order_by("-booking__booked_at")
        paid = dict(PaymentAllocation.objects.filter(participant__pilgrim=pilgrim, payment__status="VERIFIED").values_list("participant_id").annotate(t=Sum("amount_idr")))
        trips = [{
            "booking": {"id": str(p.booking_id), "code": p.booking.code, "status": p.booking.status, "booked_at": p.booking.booked_at.isoformat()},
            "departure": {"id": str(p.booking.departure_id), "code": p.booking.departure.code, "start_at": p.booking.departure.start_at.isoformat(), "status": p.booking.departure.status},
            "package": p.booking.departure.package.name, "room_type": p.pricing_snapshot_json.get("room_type", ""), "participant_status": p.participant_status,
            "price_idr": participant_net(p.pricing_snapshot_json) if p.pricing_snapshot_json.get("unit_price_idr") is not None else None, "paid_idr": paid.get(p.pk, 0),
        } for p in participations]
        documents = [{"kind": d.kind, "version": d.version, "status": d.status, "uploaded_at": d.created_at.isoformat(),
                      "expires_at": d.expires_at.isoformat() if d.expires_at else None} for d in pilgrim.documents.order_by("-created_at")[:50]]
        from modules.portal.services import change_request_payload

        changes = [change_request_payload(r) for r in pilgrim.change_requests.all()[:20]]
        family = family_payload(pilgrim.family) if pilgrim.family_id else None
        return Response({"trips": trips, "completed_trips": sum(1 for t in trips if t["participant_status"] == "COMPLETED"), "documents": documents, "change_requests": changes, "family": family})


EXPORT_COLUMNS = [("code", "Kode"), ("name", "Nama"), ("gender", "L/P"), ("birth_date", "Tanggal lahir"), ("birth_place", "Tempat lahir"), ("phone", "Telepon"),
                  ("email", "Email"), ("address", "Alamat"), ("identity", "NIK"), ("passport", "Paspor"), ("passport_expires_at", "Paspor berlaku s.d."),
                  ("family", "Keluarga"), ("family_relation", "Hubungan"), ("status", "Status")]


class PilgrimExportView(APIView):
    """GET /pilgrims/export?file=csv|xlsx[&pii=1] — ekspor terotorisasi (`pilgrims.export`), diaudit."""

    permission_classes = [IsAuthenticated, require_permission("pilgrims.export")]

    def get(self, request):
        file = request.query_params.get("file", "csv")
        if file not in {"csv", "xlsx"}:
            raise ValidationError({"file": "Format ekspor: csv atau xlsx."})
        pii = request.query_params.get("pii") == "1"
        if pii and not has_permission(permission_list(request.membership.role), "reports.export_pii"):
            raise ValidationError({"pii": "Ekspor NIK/paspor lengkap memerlukan izin reports.export_pii."})
        rows = Pilgrim.objects.filter(environment=resolve_active_environment(request.tenant)).select_related("family").order_by("name", "code")

        def value(p, key):
            if key == "identity":
                return decrypt_pii(p.identity_encrypted) if pii and p.identity_encrypted else p.identity_masked
            if key == "passport":
                return decrypt_pii(p.passport_encrypted) if pii and p.passport_encrypted else p.passport_masked
            if key == "family":
                return p.family.name if p.family_id else ""
            raw = getattr(p, key)
            return raw.isoformat() if hasattr(raw, "isoformat") else (raw or "")

        data = [[value(p, key) for key, _ in EXPORT_COLUMNS] for p in rows]
        log_event(action="pilgrims.exported", request=request, object_type="pilgrim", changes={"format": file, "rows": len(data), "pii": pii})
        stamp = timezone.localdate().isoformat()
        if file == "csv":
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow([label for _, label in EXPORT_COLUMNS])
            for row in data:
                writer.writerow([("'" + str(cell)) if str(cell)[:1] in "=+-@" else cell for cell in row])  # cegah injeksi formula
            response = HttpResponse("﻿" + buffer.getvalue(), content_type="text/csv; charset=utf-8")
        else:
            from openpyxl import Workbook

            book = Workbook()
            sheet = book.active
            sheet.title = "Jamaah"
            sheet.append([label for _, label in EXPORT_COLUMNS])
            for row in data:
                sheet.append([str(cell) for cell in row])
            out = io.BytesIO()
            book.save(out)
            response = HttpResponse(out.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = f'attachment; filename="jamaah-{stamp}.{file}"'
        response["Cache-Control"] = "private, no-store"
        return response
