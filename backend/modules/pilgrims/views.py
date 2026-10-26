"""Jamaah & dokumen — Spec §8.3 (GET/POST /pilgrims, GET/PATCH /pilgrims/{id}).

Keamanan (§10.1): NIK/paspor hanya masuk lewat field write-only, disimpan
terenkripsi, respons SELALU masked; audit memakai masked. Duplikat identitas
ditandai `possible_duplicate_of` — tidak pernah digabung otomatis (MOD-04).
Environment write di-resolve server-side (trial → demo; pasca-konversi →
production; demo READ_ONLY ditolak — §2.2).
"""
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.booking.models import BookingParticipant
from modules.notifications.services import document_reviewed
from modules.pilgrims.crypto import encrypt_pii, identity_hash, mask_last4
from modules.pilgrims.models import (
    Pilgrim,
    PilgrimDocument,
    generate_pilgrim_code,
)
from modules.pilgrims.serializers import (
    PilgrimDocumentRegisterSerializer,
    PilgrimDocumentReviewSerializer,
    PilgrimWriteSerializer,
    document_payload,
    pilgrim_payload,
)
from modules.pilgrims.services import assert_environment_writable, resolve_active_environment
from modules.tenants.models import Environment
from modules.tenants.rbac import require_permission


def _get_pilgrim(pilgrim_id, *, for_update=False) -> Pilgrim:
    try:
        queryset = Pilgrim.objects.select_for_update() if for_update else Pilgrim.objects.all()
        return queryset.get(pk=pilgrim_id)
    except (Pilgrim.DoesNotExist, ValueError, ValidationError):
        raise NotFound("Jamaah tidak ditemukan.") from None


def _apply_identity(pilgrim: Pilgrim, validated: dict) -> tuple[bool, str]:
    """Tulis field sensitif dari `validated` ke model. Return (berubah, ringkasan)."""
    changed = False
    summary = ""
    if "identity_number" in validated:
        digits = validated.pop("identity_number") or ""
        pilgrim.identity_encrypted = encrypt_pii(digits) if digits else ""
        pilgrim.identity_masked = mask_last4(digits)
        pilgrim.identity_hash = identity_hash(pilgrim.tenant_id, digits)
        changed = True
        summary = "identity diubah"
    if "passport_number" in validated:
        passport = validated.pop("passport_number") or ""
        pilgrim.passport_encrypted = encrypt_pii(passport) if passport else ""
        pilgrim.passport_masked = mask_last4(passport)
        changed = True
        if not summary:
            summary = "paspor diubah"
    return changed, summary


def _mark_duplicate(pilgrim: Pilgrim) -> bool:
    """Tandai `possible_duplicate_of` bila identitas sama sudah ada (MOD-04)."""
    if not pilgrim.identity_hash:
        return False
    existing = (
        Pilgrim.objects.filter(
            tenant_id=pilgrim.tenant_id,
            environment=pilgrim.environment,
            identity_hash=pilgrim.identity_hash,
        )
        .exclude(pk=pilgrim.pk)
        .order_by("created_at")
        .first()
    )
    if existing and pilgrim.possible_duplicate_of_id != existing.pk:
        pilgrim.possible_duplicate_of = existing
        return True
    return False


class PilgrimListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), require_permission("pilgrims.write")()]
        return [IsAuthenticated(), require_permission("pilgrims.read")()]

    def get(self, request):
        """Daftar + pencarian normalisasi aman (§5.2): nama/kode/telepon, atau
        NIK exact via hash — tanpa pernah mengekspos/men-dekripsi nilai mentah."""
        qs = Pilgrim.objects.annotate(
            in_booking=Exists(BookingParticipant.objects.filter(pilgrim_id=OuterRef("pk"))),
            has_documents=Exists(PilgrimDocument.objects.filter(pilgrim_id=OuterRef("pk"))),
        )
        env = request.query_params.get("environment", "").strip()
        if env:
            if env not in Environment.values:
                raise ValidationError({"environment": "Nilai tidak dikenal (demo/production)."})
            qs = qs.filter(environment=env)
        status_filter = request.query_params.get("status", "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        q = request.query_params.get("q", "").strip()
        if q:
            from django.db.models import Q

            digits = "".join(ch for ch in q if ch.isdigit())
            lookup = Q(name__icontains=q) | Q(code__icontains=q) | Q(phone__icontains=q)
            if len(digits) == 16:
                lookup |= Q(identity_hash=identity_hash(request.tenant.pk, digits))
            qs = qs.filter(lookup)
        rows = qs.order_by("name", "code")[:200]
        return Response({"results": [pilgrim_payload(p, include_restricted=False) for p in rows]})

    def post(self, request):
        serializer = PilgrimWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        environment = resolve_active_environment(request.tenant)
        assert_environment_writable(request.tenant, environment)

        pilgrim = Pilgrim(tenant=request.tenant, environment=environment)
        _apply_identity(pilgrim, validated)
        for field, value in validated.items():
            setattr(pilgrim, field, value)
        for _attempt in range(3):
            pilgrim.code = generate_pilgrim_code()
            try:
                with transaction.atomic():
                    pilgrim.save()
            except IntegrityError:
                continue  # tabrakan kode random → coba lagi
            break
        else:
            raise ValidationError({"code": "Gagal membuat kode jamaah unik, coba lagi."})

        _mark_duplicate(pilgrim)
        if pilgrim.possible_duplicate_of_id:
            pilgrim.save(update_fields=["possible_duplicate_of"])
        log_event(
            action="pilgrims.created",
            request=request,
            object_type="pilgrim",
            object_id=pilgrim.pk,
            changes={"code": pilgrim.code, "name": pilgrim.name, "duplicate": bool(pilgrim.possible_duplicate_of_id)},
        )
        return Response(pilgrim_payload(pilgrim), status=status.HTTP_201_CREATED)


class PilgrimDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method in {"PATCH", "DELETE"}:
            return [IsAuthenticated(), require_permission("pilgrims.write")()]
        return [IsAuthenticated(), require_permission("pilgrims.read")()]

    def get(self, request, pilgrim_id):
        return Response(pilgrim_payload(_get_pilgrim(pilgrim_id)))

    @transaction.atomic
    def patch(self, request, pilgrim_id):
        pilgrim = _get_pilgrim(pilgrim_id, for_update=True)
        assert_environment_writable(request.tenant, pilgrim.environment)
        serializer = PilgrimWriteSerializer(pilgrim, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        identity_changed, summary = _apply_identity(pilgrim, validated)
        for field, value in validated.items():
            setattr(pilgrim, field, value)
        _mark_duplicate(pilgrim)
        pilgrim.save()
        changes = {"code": pilgrim.code, "fields": sorted(set(request.data.keys()))}
        if identity_changed:
            changes["identity_change"] = summary
        log_event(
            action="pilgrims.updated",
            request=request,
            object_type="pilgrim",
            object_id=pilgrim.pk,
            changes=changes,
        )
        return Response(pilgrim_payload(pilgrim))

    @transaction.atomic
    def delete(self, request, pilgrim_id):
        """Hapus entri keliru/duplikat yang belum dipakai; selebihnya arsipkan."""
        pilgrim = _get_pilgrim(pilgrim_id, for_update=True)
        assert_environment_writable(request.tenant, pilgrim.environment)
        if pilgrim.booking_participations.exists() or pilgrim.documents.exists():
            raise ValidationError({"pilgrim": "Jamaah sudah memiliki booking atau dokumen. Ubah status menjadi Arsip agar riwayat tetap utuh."})
        # Kode saja: audit tidak menyimpan nama/NIK jamaah yang dihapus.
        log_event(action="pilgrims.deleted", request=request, object_type="pilgrim", object_id=pilgrim.pk, changes={"code": pilgrim.code})
        pilgrim.delete()
        return Response(status=204)


class PilgrimDocumentListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), require_permission("pilgrims.write")()]
        return [IsAuthenticated(), require_permission("pilgrims.read")()]

    def get(self, request, pilgrim_id):
        pilgrim = _get_pilgrim(pilgrim_id)
        docs = PilgrimDocument.objects.filter(pilgrim=pilgrim)
        return Response({"results": [document_payload(d) for d in docs]})

    def post(self, request, pilgrim_id):
        pilgrim = _get_pilgrim(pilgrim_id)
        assert_environment_writable(request.tenant, pilgrim.environment)
        serializer = PilgrimDocumentRegisterSerializer(data=request.data, context={"pilgrim": pilgrim})
        serializer.is_valid(raise_exception=True)
        last = (
            PilgrimDocument.objects.filter(pilgrim=pilgrim, kind=serializer.validated_data["kind"])
            .order_by("-version")
            .first()
        )
        doc = PilgrimDocument.objects.create(
            tenant=request.tenant,
            pilgrim=pilgrim,
            environment=pilgrim.environment,
            kind=serializer.validated_data["kind"],
            object_key=serializer.validated_data["object_key"],
            version=(last.version + 1) if last else 1,
        )
        log_event(
            action="pilgrim_documents.registered",
            request=request,
            object_type="pilgrim_document",
            object_id=doc.pk,
            changes={"kind": doc.kind, "version": doc.version, "pilgrim_code": pilgrim.code},
        )
        return Response(document_payload(doc), status=status.HTTP_201_CREATED)


class PilgrimDocumentReviewView(APIView):
    """Review berkas jamaah — role Document Reviewer (`documents.review`, §3)."""

    permission_classes = [IsAuthenticated, require_permission("documents.review")]

    def patch(self, request, pilgrim_id, document_id):
        pilgrim = _get_pilgrim(pilgrim_id)
        try:
            doc = PilgrimDocument.objects.get(pk=document_id, pilgrim=pilgrim)
        except (PilgrimDocument.DoesNotExist, ValueError, ValidationError):
            raise NotFound("Dokumen tidak ditemukan.") from None
        assert_environment_writable(request.tenant, doc.environment)
        serializer = PilgrimDocumentReviewSerializer(doc, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        doc.status = serializer.validated_data["status"]
        doc.reason = serializer.validated_data.get("reason", doc.reason)
        doc.reviewed_by = request.user
        doc.reviewed_at = timezone.now()
        doc.save()
        document_reviewed(doc)
        log_event(
            action="pilgrim_documents.reviewed",
            request=request,
            object_type="pilgrim_document",
            object_id=doc.pk,
            changes={"kind": doc.kind, "version": doc.version, "status": doc.status},
        )
        return Response(document_payload(doc))
