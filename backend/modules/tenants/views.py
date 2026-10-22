"""Tenant API — Spec §8.1: /workspaces/switch, /memberships (baca).

Endpoint tulis memberships (invite/role/revoke) & /tenant/settings → S05–S06.
"""
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.tenants.exceptions import TenantAccessDenied
from modules.tenants.models import MembershipStatus, TenantMembership
from modules.tenants.rbac import permission_list, require_permission


class SwitchWorkspaceSerializer(serializers.Serializer):
    slug = serializers.CharField(max_length=63)


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
        return Response({"active": _tenant_payload(membership)}, status=status.HTTP_200_OK)


class ListMembershipsView(APIView):
    """GET /memberships — daftar staf workspace aktif (Role: Owner/Admin §8.1).

    Menggunakan manager scoped default: otomatis terbatas ke context tenant
    saat ini (deny tanpa context — RBAC `memberships.read` menegakkannya dulu).
    """

    permission_classes = [IsAuthenticated, require_permission("memberships.read")]

    def get(self, request):
        rows = (
            TenantMembership.objects.select_related("user", "role")
            .order_by("user__email")
        )
        return Response(
            {
                "results": [
                    {
                        "user": {
                            "id": str(m.user_id),
                            "email": m.user.email,
                            "full_name": m.user.full_name,
                        },
                        "role": m.role.name if m.role else None,
                        "status": m.status,
                        "permissions": permission_list(m.role),
                    }
                    for m in rows
                ]
            },
            status=status.HTTP_200_OK,
        )
