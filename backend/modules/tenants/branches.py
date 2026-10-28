"""API Cabang (MOD-03): GET/POST /branches, PATCH /branches/{id}, POST /memberships/{id}/branch.

Grant `branches.read` (staf operasional) dan `branches.manage` (Owner/Admin).
Cabang tidak dihapus setelah dipakai transaksi; nonaktifkan agar riwayat utuh.

Cakupan cabang (TBD-08 opsi C, ADR-0019): role `ALL` melihat semua cabang; role
`OWN` hanya melihat transaksi cabang yang ditugaskan kepadanya **dan** transaksi
tanpa cabang (pusat/data lama). Travel tanpa cabang aktif tidak terpengaruh.
Data induk (paket, keberangkatan, jamaah, agen) tetap dipakai bersama.
"""
from django.db import IntegrityError, transaction
from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.tenants.exceptions import TenantContextRequired
from modules.tenants.models import Branch, MembershipBranch, TenantMembership
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


_UNSET = object()


def branch_scope(request):
    """None = tanpa batas; set UUID = cabang yang boleh dilihat (selain data tanpa cabang)."""
    cached = getattr(request, "_branch_scope", _UNSET)
    if cached is not _UNSET:
        return cached
    membership = getattr(request, "membership", None)
    role = membership.role if membership is not None else None
    scope = None
    if role is not None and role.name != "Owner" and role.branch_scope == "OWN" and Branch.objects.filter(active=True).exists():
        scope = set(MembershipBranch.objects.filter(membership=membership).values_list("branch_id", flat=True))
    request._branch_scope = scope
    return scope


def scope_filter(queryset, request, path="branch"):
    """Saring queryset ke cakupan cabang staf (`path` = jalur FK ke Branch)."""
    scope = branch_scope(request)
    if scope is None:
        return queryset
    return queryset.filter(Q(**{f"{path}_id__in": scope}) | Q(**{f"{path}__isnull": True}))


def assert_branch_allowed(request, branch):
    """Tolak penulisan transaksi ke cabang di luar cakupan staf."""
    scope = branch_scope(request)
    if scope is not None and branch is not None and branch.pk not in scope:
        raise PermissionDenied("Cabang ini di luar cakupan akses Anda.")
    if scope and branch is None:  # staf cabang tidak mencatat transaksi pusat
        raise PermissionDenied("Pilih salah satu cabang Anda.")
    return branch


def has_full_scope(request) -> bool:
    return branch_scope(request) is None


def require_full_scope(request, label):
    """Data lintas cabang (buku kas, manifest resmi, laporan keuangan) khusus cakupan semua cabang."""
    if not has_full_scope(request):
        raise PermissionDenied(f"{label} memerlukan akses semua cabang.")


def default_branch(request):
    """Cabang default staf (bila masih aktif) — isian awal transaksi baru."""
    membership = getattr(request, "membership", None)
    branch = membership.branch if membership is not None and membership.branch_id else None
    if branch is None or not branch.active:
        return None
    scope = branch_scope(request)
    return branch if scope is None or branch.pk in scope else None


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


class MyBranchesView(APIView):
    """GET /branches/mine — cakupan cabang staf saat ini (untuk pilihan cabang di UI)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.membership is None:
            raise TenantContextRequired()
        scope = branch_scope(request)
        rows = Branch.objects.filter(active=True).order_by("code")
        if scope is not None:
            rows = rows.filter(pk__in=scope)
        default = default_branch(request)
        return Response({"scope": "ALL" if scope is None else "OWN", "branches": [branch_ref(b) for b in rows], "default": branch_ref(default)})


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

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT, description="`branches`: daftar cabang yang ditugaskan (cakupan role OWN); `branch`: cabang default (otomatis ikut ditugaskan).")
    @transaction.atomic
    def post(self, request, membership_id):
        membership = TenantMembership.objects.filter(pk=membership_id).select_related("user").first()
        if membership is None:
            raise NotFound("Anggota tidak ditemukan di workspace ini.")
        if "branches" in request.data:
            ids = request.data.get("branches") or []
            if not isinstance(ids, list):
                raise ValidationError({"branches": "Harus berupa daftar cabang."})
            wanted = [resolve_branch(value, field="branches") for value in dict.fromkeys(ids)]
        else:
            wanted = [b.branch for b in membership.branch_assignments.select_related("branch")]
        default = resolve_branch(request.data.get("branch")) if "branch" in request.data else membership.branch
        if default is not None and default not in wanted:
            wanted.append(default)
        MembershipBranch.objects.filter(membership=membership).exclude(branch__in=wanted).delete()
        for branch in wanted:
            MembershipBranch.objects.get_or_create(tenant_id=membership.tenant_id, membership=membership, branch=branch)
        membership.branch = default
        membership.save(update_fields=["branch", "updated_at"])
        log_event(action="memberships.branch_changed", request=request, object_type="membership", object_id=membership.pk,
                  changes={"email": membership.user.email, "branch": default.code if default else None, "branches": sorted(b.code for b in wanted)})
        return Response({"id": str(membership.pk), "branch": branch_ref(membership.branch), "branches": [branch_ref(b) for b in sorted(wanted, key=lambda b: b.code)]})
