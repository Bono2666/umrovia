"""Tenant API — /workspaces/switch, /memberships (S03, Spec §8.1)."""
from django.urls import path

from modules.tenants import views

app_name = "tenants"

urlpatterns = [
    path("workspaces/switch", views.SwitchWorkspaceView.as_view(), name="workspace-switch"),
    path("memberships", views.ListMembershipsView.as_view(), name="memberships-list"),
]
