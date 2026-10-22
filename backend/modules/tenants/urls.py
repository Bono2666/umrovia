"""Tenant API — Spec §8.1: /workspaces/switch, /memberships, /tenant/settings, /roles."""
from django.urls import path

from modules.tenants import views

app_name = "tenants"

urlpatterns = [
    path("workspaces/switch", views.SwitchWorkspaceView.as_view(), name="workspace-switch"),
    path("memberships", views.ListCreateMembershipsView.as_view(), name="memberships"),
    path(
        "memberships/<uuid:membership_id>",
        views.MembershipDetailView.as_view(),
        name="memberships-detail",
    ),
    path("tenant/settings", views.TenantSettingsView.as_view(), name="tenant-settings"),
    path("roles", views.ListCreateRolesView.as_view(), name="roles-list-create"),
    path("roles/<uuid:role_id>", views.RoleDetailView.as_view(), name="roles-detail"),
]
