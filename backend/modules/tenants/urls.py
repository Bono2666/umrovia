"""Tenant API — Spec §8.1: /workspaces/switch, /memberships, /tenant/settings, /roles."""
from django.urls import path

from modules.tenants import branches, views

app_name = "tenants"

urlpatterns = [
    path("workspaces/switch", views.SwitchWorkspaceView.as_view(), name="workspace-switch"),
    path("memberships", views.ListCreateMembershipsView.as_view(), name="memberships"),
    path(
        "memberships/<uuid:membership_id>",
        views.MembershipDetailView.as_view(),
        name="memberships-detail",
    ),
    path("branches", branches.BranchListCreateView.as_view(), name="branches"),
    path("branches/<uuid:branch_id>", branches.BranchDetailView.as_view(), name="branch-detail"),
    path("memberships/<uuid:membership_id>/branch", branches.MembershipBranchView.as_view(), name="membership-branch"),
    path("memberships/<uuid:membership_id>/logins", views.MembershipSecurityView.as_view(action="logins"), name="membership-logins"),
    *[path(f"memberships/<uuid:membership_id>/{action}", views.MembershipSecurityView.as_view(action=action), name=f"membership-{action}") for action in ["suspend", "reactivate", "revoke-sessions", "reset-password"]],
    path("tenant/settings", views.TenantSettingsView.as_view(), name="tenant-settings"),
    path("roles", views.ListCreateRolesView.as_view(), name="roles-list-create"),
    path("roles/<uuid:role_id>", views.RoleDetailView.as_view(), name="roles-detail"),
]
