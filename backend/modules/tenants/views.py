"""Tenant API — Spec §8.1: /workspaces/switch, /memberships, /tenant/settings,
/roles (S03: switch+baca; S05: tulis staf/role/settings — RBAC + audit).

Guard IDOR: semua fetch objek memakai manager scoped / filter `tenant=` dari
context request — id asing → 404, tanpa kebocoran lintas-tenant.
"""
import re

from django.db import transaction
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.audit.services import log_event
from modules.tenants import services
from modules.tenants.exceptions import TenantAccessDenied
from modules.tenants.models import MembershipStatus, Role, TenantMembership, TenantSettings
from modules.tenants.rbac import has_permission, permission_list, require_permission

# Batas ukuran JSON settings (mencegah payload raksasa) — bytes ter-serialize.
_MAX_SECTION_BYTES = 16_384
# Pola permission `domain(.object).action` (§3); wildcard antar-segmen diizinkan,
# tetapi grant tunggal `*` DILARANG untuk role buatan user (hanya Owner sistem).
_PERMISSION_PATTERN = re.compile(r"^[a-z_]+(\.(\*|[a-z_]+))*$")
_MAX_ROLE_PERMISSIONS = 64


def _validate_section(value, field: str) -> dict:
    import json

    if not isinstance(value, dict):
        raise serializers.ValidationError({field: "Harus berupa objek JSON."})
    if len(json.dumps(value)) > _MAX_SECTION_BYTES:
        raise serializers.ValidationError({field: f"Melebihi {_MAX_SECTION_BYTES} byte."})
    return value


def _validate_permissions(value) -> list[str]:
    if not isinstance(value, list) or not value:
        raise serializers.ValidationError({"permissions": "Harus berupa daftar permission (non-kosong)."})
    if len(value) > _MAX_ROLE_PERMISSIONS:
        raise serializers.ValidationError({"permissions": f"Maksimal {_MAX_ROLE_PERMISSIONS} permission."})
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str) or not _PERMISSION_PATTERN.match(item):
            raise serializers.ValidationError(
                {"permissions": f"Format permission tidak valid: {item!r} (contoh: bookings.create, reports.*)."}
            )
        if item == "*":
            raise serializers.ValidationError({"permissions": "Wildcard '*' hanya untuk role Owner sistem."})
        if item not in cleaned:
            cleaned.append(item)
    return cleaned


class SwitchWorkspaceSerializer(serializers.Serializer):
    slug = serializers.CharField(max_length=63)


class TenantSettingsSerializer(serializers.Serializer):
    """PATCH parsial: hanya bagian yang dikirim yang diganti seluruhnya (§5.1)."""

    branding_json = serializers.DictField(required=False)
    invoice_config_json = serializers.DictField(required=False)
    rules_json = serializers.DictField(required=False)

    def validate_branding_json(self, value):
        return _validate_section(value, "branding_json")

    def validate_invoice_config_json(self, value):
        return _validate_section(value, "invoice_config_json")

    def validate_rules_json(self, value):
        if isinstance(value, dict) and "payments" in value:
            from modules.payments.policy import validate_payment_rules

            validate_payment_rules(value["payments"])
        return _validate_section(value, "rules_json")


class CreateMembershipSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role_id = serializers.UUIDField()


class ChangeMembershipRoleSerializer(serializers.Serializer):
    role_id = serializers.UUIDField()


class RoleNameMixin:
    def validate_name(self, value) -> str:
        name = value.strip()
        if not name or name.lower() == "owner":
            raise serializers.ValidationError("Nama role tidak valid ('Owner' dilindungi sistem).")
        return name


class CreateRoleSerializer(RoleNameMixin, serializers.Serializer):
    name = serializers.CharField(max_length=64)
    permissions = serializers.ListField(child=serializers.CharField(max_length=64), required=False)

    def validate_permissions(self, value):
        return _validate_permissions(value) if value is not None else []


class UpdateRoleSerializer(RoleNameMixin, serializers.Serializer):
    name = serializers.CharField(max_length=64, required=False)
    permissions = serializers.ListField(child=serializers.CharField(max_length=64), required=False)

    def validate_permissions(self, value):
        return _validate_permissions(value) if value else []


def _assert_grant_scope(request, grants, previous=()):
    actor_grants = permission_list(request.membership.role)
    for grant in set(grants) - set(previous):
        if not has_permission(actor_grants, grant):
            raise PermissionDenied("Anda hanya dapat memberikan izin yang tercakup dalam hak akses Anda.")


def _tenant_payload(membership: TenantMembership) -> dict:
    return {
        "tenant": {
            "id": str(membership.tenant_id),
            "slug": membership.tenant.slug,
            "display_name": membership.tenant.display_name,
            "state": membership.tenant.state,
        },
        "role": membership.role.name if membership.role else None,
        "status": membership.status,
        "permissions": permission_list(membership.role),
        "branch_id": str(membership.branch_id) if membership.branch_id else None,
    }


def _membership_row(m: TenantMembership) -> dict:
    return {
        "id": str(m.id),
        "user": {
            "id": str(m.user_id),
            "email": m.user.email,
            "full_name": m.user.full_name,
        },
        "role": m.role.name if m.role else None,
        "role_id": str(m.role_id) if m.role_id else None,
        "branch": {"id": str(m.branch_id), "code": m.branch.code, "name": m.branch.name} if m.branch_id else None,
        "status": m.status,
        "permissions": permission_list(m.role),
    }


def _settings_payload(settings_row: TenantSettings) -> dict:
    return {
        "branding_json": settings_row.branding_json,
        "invoice_config_json": settings_row.invoice_config_json,
        "rules_json": settings_row.rules_json,
    }


def _role_payload(role: Role) -> dict:
    return {
        "id": str(role.id),
        "name": role.name,
        "is_system": role.is_system,
        "permissions": permission_list(role),
    }


class SwitchWorkspaceView(APIView):
    """POST /workspaces/switch — pindah workspace eksplisit (Role: Member, §8.1).

    Nilai sesi divalidasi terhadap membership ACTIVE di server; slug asing/tak
    dikenal → TENANT_ACCESS_DENIED (kode sama — tanpa oracle enumerasi).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SwitchWorkspaceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        slug = serializer.validated_data["slug"]
        membership = (
            TenantMembership.objects.without_tenant_guard()
            .filter(user=request.user, status=MembershipStatus.ACTIVE, tenant__slug=slug)
            .select_related("tenant", "role")
            .first()
        )
        if membership is None:
            raise TenantAccessDenied()
        request.session["active_tenant_slug"] = membership.tenant.slug
        request.session.modified = True
        log_event(
            action="workspaces.switched",
            request=request,
            tenant=membership.tenant,
            object_type="tenant",
            object_id=membership.tenant_id,
            changes={"slug": membership.tenant.slug},
        )
        return Response({"active": _tenant_payload(membership)}, status=status.HTTP_200_OK)


class ListCreateMembershipsView(APIView):
    """GET/POST /memberships — daftar & undang staf (Role: Owner/Admin §8.1).

    GET memakai manager scoped default: otomatis terbatas ke context tenant
    saat ini. POST: user baru → akun `PENDING_VERIFICATION` + membership
    `INVITED` (aktif saat email diverifikasi); user ACTIVE → membership
    `ACTIVE`. Guard kuota trial (TR04) → 403 TRIAL_USER_LIMIT.
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), require_permission("memberships.write")()]
        return [IsAuthenticated(), require_permission("memberships.read")()]

    def get(self, request):
        rows = TenantMembership.objects.select_related("user", "role", "branch").order_by("user__email")
        return Response({"results": [_membership_row(m) for m in rows]}, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = CreateMembershipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = Role.objects.filter(tenant=request.tenant, id=serializer.validated_data["role_id"]).first()
        membership, created_user = services.invite_member(
            tenant=request.tenant,
            email=serializer.validated_data["email"],
            role=role,
        )
        log_event(
            action="memberships.invited",
            request=request,
            object_type="membership",
            object_id=membership.id,
            changes={
                "email": membership.user.email,
                "role": membership.role.name,
                "status": membership.status,
                "user_created": created_user,
            },
        )
        return Response({"membership": _membership_row(membership)}, status=status.HTTP_201_CREATED)


class MembershipDetailView(APIView):
    """PATCH /memberships/{id} (ganti role) & DELETE (revoke) — Role: Owner §8.1.

    Owner terakhir tidak bisa diturunkan/dicabut (anti workspace yatim).
    Membership tenant lain → 404 (scoped manager).
    """

    permission_classes = [IsAuthenticated, require_permission("memberships.manage")]

    def _get(self, tenant, pk):
        membership = TenantMembership.objects.filter(pk=pk).select_related("user", "role").first()
        if membership is None:
            raise NotFound("Anggota tidak ditemukan di workspace ini.")
        return membership

    def patch(self, request, membership_id):
        serializer = ChangeMembershipRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = self._get(request.tenant, membership_id)
        role = Role.objects.filter(tenant=request.tenant, id=serializer.validated_data["role_id"]).first()
        old_role = services.assign_membership_role(tenant=request.tenant, membership=membership, role=role)
        log_event(
            action="memberships.role_changed",
            request=request,
            object_type="membership",
            object_id=membership.id,
            changes={"email": membership.user.email, "from_role": old_role, "to_role": membership.role.name},
        )
        return Response({"membership": _membership_row(membership)}, status=status.HTTP_200_OK)

    def delete(self, request, membership_id):
        membership = self._get(request.tenant, membership_id)
        changed = services.revoke_membership(tenant=request.tenant, membership=membership)
        if changed:
            log_event(
                action="memberships.revoked",
                request=request,
                object_type="membership",
                object_id=membership.id,
                changes={"email": membership.user.email, "role": membership.role.name},
            )
        return Response(
            {"membership": _membership_row(membership), "changed": changed},
            status=status.HTTP_200_OK,
        )


class TenantSettingsView(APIView):
    """GET/PATCH /tenant/settings — branding, invoice config, rules (§5.1/§8.1;
    Role: Owner/Admin). PATCH mengganti seluruh bagian yang dikirim."""

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsAuthenticated(), require_permission("tenant.settings.write")()]
        return [IsAuthenticated(), require_permission("tenant.settings.read")()]

    def get(self, request):
        settings_row, _ = TenantSettings.objects.get_or_create(tenant=request.tenant)
        return Response(_settings_payload(settings_row), status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = TenantSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data:
            raise serializers.ValidationError({"detail": "Tidak ada bagian settings yang dikirim."})
        settings_row, _ = TenantSettings.objects.get_or_create(tenant=request.tenant)
        for field, value in serializer.validated_data.items():
            setattr(settings_row, field, value)
        settings_row.save()
        log_event(
            action="tenant.settings.updated",
            request=request,
            object_type="tenant_settings",
            object_id=request.tenant.pk,
            changes={"updated_sections": sorted(serializer.validated_data.keys())},
        )
        return Response(_settings_payload(settings_row), status=status.HTTP_200_OK)


class ListCreateRolesView(APIView):
    """GET/POST /roles — daftar & buat role custom (§5.1 roles; Role: Owner/Admin).

    Grant wildcard '*' hanya role Owner sistem; permission tervalidasi pola §3.
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), require_permission("roles.write")()]
        return [IsAuthenticated(), require_permission("roles.read")()]

    @staticmethod
    def _payload(role: Role) -> dict:
        return _role_payload(role)

    def get(self, request):
        roles = Role.objects.filter(tenant=request.tenant).order_by("name")
        return Response({"results": [self._payload(r) for r in roles]}, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = CreateRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data["name"]
        _assert_grant_scope(request, serializer.validated_data.get("permissions", []))
        if Role.objects.filter(tenant=request.tenant, name=name).exists():
            raise serializers.ValidationError({"name": f"Role '{name}' sudah ada di workspace ini."})
        role = Role.objects.create(
            tenant=request.tenant,
            name=name,
            permissions_json=serializer.validated_data.get("permissions", []),
            is_system=False,
        )
        log_event(
            action="roles.created",
            request=request,
            object_type="role",
            object_id=role.id,
            changes={"name": role.name, "permissions": permission_list(role)},
        )
        return Response({"role": self._payload(role)}, status=status.HTTP_201_CREATED)


class RoleDetailView(APIView):
    """PATCH/DELETE /roles/{id} — Role: Owner/Admin (§5.1; system role dilindungi:
    nama/permission Owner tak bisa diubah; role terpakai tak bisa dihapus)."""

    permission_classes = [IsAuthenticated, require_permission("roles.write")]

    def _get(self, tenant, pk):
        role = Role.objects.filter(tenant=tenant, id=pk).first()
        if role is None:
            raise NotFound("Role tidak ditemukan di workspace ini.")
        return role

    @transaction.atomic
    def patch(self, request, role_id):
        role = self._get(request.tenant, role_id)
        role = Role.objects.select_for_update().get(pk=role.pk)
        if role.is_system or role.name == "Owner":
            raise ValidationError({"role": "Role sistem tidak bisa diubah."})
        serializer = UpdateRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        before = {"name": role.name, "permissions": permission_list(role)}
        _assert_grant_scope(request, serializer.validated_data.get("permissions", []), previous=before["permissions"])
        new_name = serializer.validated_data.get("name")
        if new_name and Role.objects.filter(tenant=request.tenant, name=new_name).exclude(pk=role.pk).exists():
            raise serializers.ValidationError({"name": f"Role '{new_name}' sudah ada di workspace ini."})
        if new_name:
            role.name = new_name
        if "permissions" in serializer.validated_data:
            role.permissions_json = serializer.validated_data["permissions"]
        role.save()
        log_event(
            action="roles.updated",
            request=request,
            object_type="role",
            object_id=role.id,
            changes={
                "name": {"from": before["name"], "to": role.name},
                "permissions_changed": before["permissions"] != permission_list(role),
            },
        )
        return Response({"role": _role_payload(role)}, status=status.HTTP_200_OK)

    def delete(self, request, role_id):
        role = self._get(request.tenant, role_id)
        if role.is_system:
            raise ValidationError({"role": "Role sistem tidak bisa dihapus."})
        if TenantMembership.objects.filter(role=role).exists():
            raise ValidationError({"role": "Role masih dipakai anggota — pindahkan role mereka dulu."})
        name = role.name
        role.delete()
        log_event(
            action="roles.deleted",
            request=request,
            object_type="role",
            object_id=role_id,
            changes={"name": name},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
