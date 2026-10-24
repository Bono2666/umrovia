"""Paket API — /packages (Spec §8.3, S08)."""
from django.urls import path

from modules.catalog import views

app_name = "catalog"

urlpatterns = [
    path("packages", views.PackageListCreateView.as_view(), name="package-list"),
    path("packages/<uuid:package_id>", views.PackageDetailView.as_view(), name="package-detail"),
]
