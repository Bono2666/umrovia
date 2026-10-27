"""API Cabang (MOD-03): GET/POST /branches, PATCH /branches/{id}, POST /memberships/{id}/branch.

Grant `branches.read` (staf operasional) dan `branches.manage` (Owner/Admin).
Cabang tidak dihapus setelah dipakai transaksi; nonaktifkan agar riwayat utuh.
"""
from django.db import IntegrityError, transaction
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.tenants.models import Branch, TenantMembership
from modules.tenants.rbac import require_permission


def branch_ref(branch):
    return {"id": str(branch.pk), "code": branch.code, "name": branch.name} if branch else None


def branch_payload(branch):
    return {
        **branch_ref(branch), "manager_name": branch.manager_name, "phone": branch.phone, "address": branch.address,
        "active": branch.active, "member_count": getattr(branch, "member_count", None),
    }


def resolve_branch(branch_id, *, field="branch"):
    """UUID → Branch aktif milik tenant (None bila kosong); asing/nonaktif → 400."""
    if not branch_id:
        return None
    branch = Branch.objects.filter(pk=branch_id).first()
    if branch is None:
        raise ValidationError({field: "Cabang tidak ditemukan."})
    if not branch.active:
        raise ValidationError({field: "Cabang tidak aktif."})
    return branch


def default_branch(request):
    """Cabang default staf (bila masih aktif) — isian awal transaksi baru."""
    membership = getattr(request, "membership", None)
    branch = membership.branch if membership is not None and membership.branch_id else None
    return branch if branch is not None and branch.active else None


class BranchSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^[A-Za-z0-9-]{2,16}$", error_messages={"invalid": "Kode 2–16 huruf/angka/tanda hubung."})
    name = serializers.CharField(max_length=120)
    manager_name = serializers.CharField(max_length=160, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    address = serializers.CharField(max_length=500, required=False, allow_blank=True)
    active = serializers.BooleanField(required=False)


def _save(branch):
    try:
        with transaction.atomic():
            branch.save()
    except IntegrityError:
        raise ValidationError({"code": "Kode cabang sudah dipakai."}) from None


class BranchListCreateView(APIView):
    def get_permissions(self):
        return [IsAuthenticated(), require_permission("branches.manage" if self.request.method == "POST" else "branches.read")()]

    @extend_schema(operation_id="branches_list", responses=OpenApiTypes.OBJECT)
    def get(self, request):
        from django.db.models import Count

        rows = Branch.objects.annotate(member_count=Count("members")).order_by("-active", "code")
        if request.query_params.get("active") == "1":
            rows = rows.filter(active=True)
        return Response({"results": [branch_payload(b) for b in rows]})

    @extend_schema(request=BranchSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request):
        serializer = BranchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = {k: v.strip() if isinstance(v, str) else v for k, v in serializer.validated_data.items()}
        data["code"] = data["code"].upper()
        branch = Branch(tenant=request.tenant, **data)
        _save(branch)
        log_event(action="branches.created", request=request, object_type="branch", object_id=branch.pk, changes={"code": branch.code, "name": branch.name})
        return Response(branch_payload(branch), status=status.HTTP_201_CREATED)


class BranchDetailView(APIView):
    permission_classes = [IsAuthenticated, require_permission("branches.manage")]

    @extend_schema(request=BranchSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request, branch_id):
        branch = Branch.objects.filter(pk=branch_id).first()
        if branch is None:
            raise NotFound("Cabang tidak ditemukan.")
        serializer = BranchSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for key, value in serializer.validated_data.items():
            setattr(branch, key, value.strip().upper() if key == "code" else value.strip() if isinstance(value, str) else value)
        _save(branch)
        log_event(action="branches.updated", request=request, object_type="branch", object_id=branch.pk, changes={"fields": sorted(serializer.validated_data)})
        return Response(branch_payload(branch))


class MembershipBranchView(APIView):
    """Cabang default staf — dipakai sebagai isian awal cabang pada transaksi baru."""

    permission_classes = [IsAuthenticated, require_permission("branches.manage")]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    def post(self, request, membership_id):
        membership = TenantMembership.objects.filter(pk=membership_id).select_related("user").first()
        if membership is None:
            raise NotFound("Anggota tidak ditemukan di workspace ini.")
        membership.branch = resolve_branch(request.data.get("branch"))
        membership.save(update_fields=["branch", "updated_at"])
        log_event(action="memberships.branch_changed", request=request, object_type="membership", object_id=membership.pk, changes={"email": membership.user.email, "branch": membership.branch.code if membership.branch else None})
        return Response({"id": str(membership.pk), "branch": branch_ref(membership.branch)})
