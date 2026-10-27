import hashlib

from django.core import signing
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.identity.models import UserStatus
from modules.payments.models import TravelInvoice, TravelReceipt
from modules.pilgrims.models import Pilgrim, PilgrimDocument
from modules.portal import files, services
from modules.portal.models import PortalAccess, PortalAccessStatus
from modules.tenants.environment import assert_environment_writable, resolve_active_environment
from modules.tenants.models import MembershipStatus, Tenant, TenantMembership
from modules.tenants.rbac import has_permission, permission_list, require_permission
from modules.wallet.services import platform_tenant_context


class ActivePortalUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.status == UserStatus.ACTIVE)


class AcceptInviteSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200)
    password = serializers.CharField(max_length=128, required=False, allow_blank=True, default="", trim_whitespace=False)
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")


class InviteSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True, default="")


class RevokeSerializer(serializers.Serializer):
    access_id = serializers.UUIDField(required=False)
    invite_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if bool(attrs.get("access_id")) == bool(attrs.get("invite_id")):
            raise serializers.ValidationError("Pilih satu akses atau satu undangan.")
        return attrs


def _pdf(request, document, number, tenant):
    data = bytes(document.pdf_data)
    if hashlib.sha256(data).hexdigest() != document.checksum:
        raise ValidationError({"document": "Checksum dokumen tidak cocok."})
    log_event(action="financial_document.downloaded", tenant=tenant, actor=request.user, object_type=document._meta.label_lower, object_id=document.pk, changes={"source": "portal"})
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{number}.pdf"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


# ------------------------------------------------------------- invitation --


class InviteInspectView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_scope = "portal-invite"

    @extend_schema(parameters=[OpenApiParameter("token", str, required=True)], responses=OpenApiTypes.OBJECT, auth=[])
    def get(self, request):
        return Response(services.inspect_invite(request.query_params.get("token", "")))


class AcceptInviteView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "portal-invite"

    @extend_schema(request=AcceptInviteSerializer, responses=OpenApiTypes.OBJECT, description="Bind the invited email to the pilgrim. New accounts set a password; existing accounts must be logged in as the invited email.")
    def post(self, request):
        serializer = AcceptInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        access = services.accept_invite(raw=serializer.validated_data["token"], request=request, password=serializer.validated_data["password"], full_name=serializer.validated_data["full_name"])
        return Response({"access_id": str(access.pk)})


# ----------------------------------------------------------------- portal --


class PortalOverviewView(APIView):
    permission_classes = [ActivePortalUser]

    @extend_schema(responses=OpenApiTypes.OBJECT, description="Own pilgrim profiles, bookings and payment progress across every active portal grant.")
    def get(self, request):
        return Response({"results": services.overview(request.user)})


class PortalDocumentsView(APIView):
    permission_classes = [ActivePortalUser]

    def get_throttles(self):
        self.throttle_scope = "portal-upload" if self.request.method == "POST" else None
        return super().get_throttles() if self.throttle_scope else []

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @transaction.atomic
    def get(self, request, access_id):
        with services.scoped_access(request.user, access_id) as (_, pilgrim):
            return Response({"results": services.documents(pilgrim)})

    @extend_schema(request={"multipart/form-data": OpenApiTypes.OBJECT}, responses={201: OpenApiTypes.OBJECT}, description="Upload PDF/JPEG/PNG (magic bytes checked, size limited). Creates a new version awaiting travel review.")
    def post(self, request, access_id):
        data, ext = files.inspect_upload(request.FILES.get("file"))
        doc = services.upload_for_access(user=request.user, access_id=access_id, kind=request.data.get("kind", ""), data=data, ext=ext)
        return Response(doc, status=201)


class PortalDocumentLinkView(APIView):
    permission_classes = [ActivePortalUser]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT, description="Signed download path (≤10 min) bound to this user; authorization is re-checked on download.")
    @transaction.atomic
    def post(self, request, access_id, document_id):
        with services.scoped_access(request.user, access_id) as (_, pilgrim):
            doc = PilgrimDocument.objects.filter(pk=document_id, pilgrim=pilgrim).first()
            if doc is None or not files.has_file(doc):
                raise NotFound("Berkas tidak ditemukan.")
            return Response({"path": files.signed_download_path(document=doc, user=request.user, scope="portal")})


class PortalProfileView(APIView):
    permission_classes = [ActivePortalUser]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT, description="Pilgrims may correct contact fields only.")
    def patch(self, request, access_id):
        if not isinstance(request.data, dict):
            raise ValidationError("Payload harus berupa objek.")
        return Response(services.update_profile(user=request.user, access_id=access_id, data=dict(request.data)))


class PortalInvoicePdfView(APIView):
    permission_classes = [ActivePortalUser]

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @transaction.atomic
    def get(self, request, access_id, invoice_id):
        with services.scoped_access(request.user, access_id) as (access, pilgrim):
            invoice = TravelInvoice.objects.filter(pk=invoice_id, lines__participant__pilgrim=pilgrim).exclude(status="VOIDED").distinct().first()
            # Invoice grup memuat jamaah lain: tidak diberikan ke portal (POR02).
            if invoice is None or invoice.lines.exclude(participant__pilgrim=pilgrim).exists():
                raise NotFound("Invoice tidak ditemukan.")
            return _pdf(request, invoice, invoice.invoice_number, Tenant.objects.get(pk=access.tenant_id))


class PortalReceiptPdfView(APIView):
    permission_classes = [ActivePortalUser]

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @transaction.atomic
    def get(self, request, access_id, receipt_id):
        with services.scoped_access(request.user, access_id) as (access, pilgrim):
            receipt = TravelReceipt.objects.filter(pk=receipt_id, payment__status="VERIFIED", payment__allocations__participant__pilgrim=pilgrim).distinct().first()
            if receipt is None or receipt.payment.allocations.exclude(participant__pilgrim=pilgrim).exists():
                raise NotFound("Kuitansi tidak ditemukan.")
            return _pdf(request, receipt, receipt.receipt_no, Tenant.objects.get(pk=access.tenant_id))


# ------------------------------------------------------------ signed file --


class SignedDocumentFileView(APIView):
    """Unduh berkas lewat token bertanda tangan: kedaluwarsa ≤10 menit, terikat
    user, dan izin dicek ulang saat diunduh (grant portal atau membership staf)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
    @transaction.atomic
    def get(self, request, token):
        try:
            payload = files.read_download_token(token)
        except signing.SignatureExpired:
            raise PermissionDenied("Tautan unduhan kedaluwarsa. Buka lagi dari halaman dokumen.") from None
        except signing.BadSignature:
            raise NotFound("Berkas tidak ditemukan.") from None
        if payload.get("u") != str(request.user.pk):
            raise NotFound("Berkas tidak ditemukan.")
        tenant_id = payload["t"]
        if payload.get("s") == "staff":
            membership = TenantMembership.objects.without_tenant_guard().filter(user=request.user, tenant_id=tenant_id, status=MembershipStatus.ACTIVE).select_related("role").first()
            if membership is None or not has_permission(permission_list(membership.role), "pilgrims.read"):
                raise NotFound("Berkas tidak ditemukan.")
        with platform_tenant_context(tenant_id) as tenant:
            doc = PilgrimDocument.objects.filter(pk=payload["d"]).first()
            if doc is None or not files.has_file(doc):
                raise NotFound("Berkas tidak ditemukan.")
            if payload.get("s") == "portal" and not PortalAccess.objects.filter(user=request.user, tenant_id=tenant_id, pilgrim_id=doc.pilgrim_id, status=PortalAccessStatus.ACTIVE).exists():
                raise NotFound("Berkas tidak ditemukan.")
            with default_storage.open(doc.object_key, "rb") as handle:
                data = handle.read()
            log_event(action="pilgrim_documents.downloaded", tenant=tenant, actor=request.user, object_type="pilgrim_document", object_id=doc.pk, changes={"kind": doc.kind, "version": doc.version, "scope": payload.get("s")})
        ext = doc.object_key.rsplit(".", 1)[-1].lower()
        response = HttpResponse(data, content_type=files.content_type(doc))
        response["Content-Disposition"] = f'attachment; filename="{doc.kind}-v{doc.version}.{ext}"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        return response


# ------------------------------------------------------------------ staff --


def _pilgrim(pilgrim_id):
    pilgrim = Pilgrim.objects.filter(pk=pilgrim_id).select_related("tenant").first()
    if pilgrim is None:
        raise NotFound("Jamaah tidak ditemukan.")
    return pilgrim


class PilgrimPortalView(APIView):
    def get_permissions(self):
        return [IsAuthenticated(), require_permission("pilgrims.write" if self.request.method == "POST" else "pilgrims.read")()]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, pilgrim_id):
        return Response(services.portal_status(_pilgrim(pilgrim_id)))

    @extend_schema(request=InviteSerializer, responses=OpenApiTypes.OBJECT, description="Email a one-time portal invite (replaces any open invite).")
    @transaction.atomic
    def post(self, request, pilgrim_id):
        serializer = InviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pilgrim = _pilgrim(pilgrim_id)
        services.invite_pilgrim(pilgrim=pilgrim, email=serializer.validated_data["email"], actor=request.user)
        return Response(services.portal_status(pilgrim), status=201)


class PilgrimPortalRevokeView(APIView):
    permission_classes = [IsAuthenticated, require_permission("pilgrims.write")]

    @extend_schema(request=RevokeSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, pilgrim_id):
        serializer = RevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pilgrim = _pilgrim(pilgrim_id)
        services.revoke_portal(pilgrim=pilgrim, actor=request.user, **serializer.validated_data)
        return Response(services.portal_status(pilgrim))


class PilgrimDocumentUploadView(APIView):
    permission_classes = [IsAuthenticated, require_permission("pilgrims.write")]
    throttle_scope = "portal-upload"

    @extend_schema(request={"multipart/form-data": OpenApiTypes.OBJECT}, responses={201: OpenApiTypes.OBJECT})
    @transaction.atomic
    def post(self, request, pilgrim_id):
        pilgrim = _pilgrim(pilgrim_id)
        assert_environment_writable(request.tenant, pilgrim.environment)
        data, ext = files.inspect_upload(request.FILES.get("file"))
        doc = files.add_uploaded_document(pilgrim_id=pilgrim.pk, kind=request.data.get("kind", ""), data=data, ext=ext)
        log_event(action="pilgrim_documents.uploaded", request=request, object_type="pilgrim_document", object_id=doc.pk, changes={"kind": doc.kind, "version": doc.version, "source": "staff"})
        from modules.pilgrims.serializers import document_payload

        return Response(document_payload(doc), status=201)


class PilgrimDocumentLinkView(APIView):
    permission_classes = [IsAuthenticated, require_permission("pilgrims.read")]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, pilgrim_id, document_id):
        doc = PilgrimDocument.objects.filter(pk=document_id, pilgrim=_pilgrim(pilgrim_id)).first()
        if doc is None or not files.has_file(doc):
            raise NotFound("Berkas tidak ditemukan.")
        return Response({"path": files.signed_download_path(document=doc, user=request.user, scope="staff")})


# ------------------------------------------------- POR-05 / POR-06 (staf & portal) --
class PortalChangeRequestView(APIView):
    """Jamaah mengajukan koreksi identitas (nama/NIK/paspor/tanggal lahir) untuk diverifikasi travel."""

    permission_classes = [ActivePortalUser]

    @extend_schema(request=OpenApiTypes.OBJECT, responses={201: OpenApiTypes.OBJECT})
    def post(self, request, access_id):
        data = request.data if isinstance(request.data, dict) else {}
        return Response(services.submit_change_request(user=request.user, access_id=access_id, data=data.get("changes") or {}, reason=data.get("reason", "")), status=201)


def _announcement_staff_payload(row):
    payload = services.announcement_payload(row)
    payload.update({"expires_at": row.expires_at.isoformat() if row.expires_at else None, "status": "DRAFT" if not row.published_at else "EXPIRED" if row.expires_at and row.expires_at <= timezone.now() else "PUBLISHED",
                    "created_by": (row.created_by.full_name or row.created_by.email) if row.created_by_id else None, "created_at": row.created_at.isoformat()})
    return payload


class AnnouncementSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160)
    body = serializers.CharField(max_length=5000)
    departure = serializers.UUIDField(required=False, allow_null=True)
    publish = serializers.BooleanField(required=False, default=True)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class AnnouncementListCreateView(APIView):
    permission_classes = [IsAuthenticated, require_permission("announcements.manage")]

    def get(self, request):
        from modules.portal.models import Announcement

        rows = Announcement.objects.filter(environment=resolve_active_environment(request.tenant)).select_related("departure", "created_by").order_by("-created_at")[:100]
        return Response({"results": [_announcement_staff_payload(r) for r in rows]})

    @transaction.atomic
    def post(self, request):
        from modules.departures.models import Departure
        from modules.portal.models import Announcement

        environment = resolve_active_environment(request.tenant)
        assert_environment_writable(request.tenant, environment)
        serializer = AnnouncementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        departure = None
        if data.get("departure"):
            departure = Departure.objects.filter(pk=data["departure"], environment=environment).first()
            if departure is None:
                raise ValidationError({"departure": "Keberangkatan tidak ditemukan."})
        if data.get("expires_at") and data["expires_at"] <= timezone.now():
            raise ValidationError({"expires_at": "Batas tayang harus di masa depan."})
        row = Announcement.objects.create(tenant=request.tenant, environment=environment, title=data["title"].strip(), body=data["body"].strip(), departure=departure,
                                          published_at=timezone.now() if data["publish"] else None, expires_at=data.get("expires_at"), created_by=request.user)
        log_event(action="announcements.created", request=request, object_type="announcement", object_id=row.pk, changes={"title": row.title, "published": bool(row.published_at)})
        return Response(_announcement_staff_payload(row), status=201)


class AnnouncementDetailView(APIView):
    permission_classes = [IsAuthenticated, require_permission("announcements.manage")]

    @transaction.atomic
    def patch(self, request, announcement_id):
        from modules.portal.models import Announcement

        row = Announcement.objects.filter(pk=announcement_id).select_related("departure", "created_by").first()
        if row is None:
            raise NotFound("Pengumuman tidak ditemukan.")
        assert_environment_writable(request.tenant, row.environment)
        action = request.data.get("action")
        if action == "publish":
            row.published_at = row.published_at or timezone.now()
        elif action == "unpublish":
            row.published_at = None
        elif action == "archive":
            row.expires_at = timezone.now()
        else:
            serializer = AnnouncementSerializer(data={"title": row.title, "body": row.body, **request.data}, partial=True)
            serializer.is_valid(raise_exception=True)
            row.title, row.body = serializer.validated_data["title"].strip(), serializer.validated_data["body"].strip()
        row.save()
        log_event(action="announcements.updated", request=request, object_type="announcement", object_id=row.pk, changes={"action": action or "edit"})
        return Response(_announcement_staff_payload(row))


class ChangeRequestListView(APIView):
    permission_classes = [IsAuthenticated, require_permission("pilgrims.write")]

    def get(self, request):
        from modules.portal.models import ProfileChangeRequest

        status_filter = request.query_params.get("status", "PENDING")
        qs = ProfileChangeRequest.objects.filter(environment=resolve_active_environment(request.tenant)).select_related("pilgrim")
        if status_filter:
            qs = qs.filter(status=status_filter)
        rows = [{**services.change_request_payload(r), "pilgrim": {"id": str(r.pilgrim_id), "code": r.pilgrim.code, "name": r.pilgrim.name}} for r in qs[:200]]
        return Response({"results": rows})


class ChangeRequestDecisionView(APIView):
    permission_classes = [IsAuthenticated, require_permission("pilgrims.write")]
    action = "approve"

    def post(self, request, request_id):
        from modules.portal.models import ProfileChangeRequest

        row = ProfileChangeRequest.objects.filter(pk=request_id, environment=resolve_active_environment(request.tenant)).first()
        if row is None:
            raise NotFound("Permintaan tidak ditemukan.")
        row = services.decide_change_request(request_id=row.pk, actor=request.user, approve=self.action == "approve", note=str(request.data.get("note") or ""), request=request)
        return Response(services.change_request_payload(row))
