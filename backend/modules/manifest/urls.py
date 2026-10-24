"""URL manifest & checklist (Spec §8.3, UI-11/UI-12).

Rute berdiri sendiri — tidak bentrok dengan `departures/` karena berpola
`departures/{id}/manifest[/publish|/export]` (segment ekstra).
"""
from django.urls import path

from modules.manifest import views

app_name = "manifest"

urlpatterns = [
    path(
        "departures/<uuid:departure_id>/manifest",
        views.ManifestView.as_view(),
        name="manifest",
    ),
    path(
        "departures/<uuid:departure_id>/manifest/publish",
        views.ManifestPublishView.as_view(),
        name="manifest-publish",
    ),
    path(
        "departures/<uuid:departure_id>/manifest/export",
        views.ManifestExportView.as_view(),
        name="manifest-export",
    ),
    path(
        "document-requirements",
        views.DocumentRequirementListCreateView.as_view(),
        name="document-requirement-list",
    ),
    path(
        "document-requirements/<uuid:requirement_id>",
        views.DocumentRequirementDetailView.as_view(),
        name="document-requirement-detail",
    ),
]
