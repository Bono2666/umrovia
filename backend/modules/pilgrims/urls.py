"""Jamaah API — /pilgrims (Spec §8.3, S07)."""
from django.urls import path

from modules.pilgrims import family, views

app_name = "pilgrims"

urlpatterns = [
    path("pilgrims", views.PilgrimListCreateView.as_view(), name="pilgrim-list"),
    path("pilgrims/export", family.PilgrimExportView.as_view(), name="pilgrim-export"),
    path("pilgrims/<uuid:pilgrim_id>/history", family.PilgrimHistoryView.as_view(), name="pilgrim-history"),
    path("families", family.FamilyListCreateView.as_view(), name="families"),
    path("families/<uuid:family_id>/members", family.FamilyMemberView.as_view(), name="family-members"),
    path("pilgrims/<uuid:pilgrim_id>", views.PilgrimDetailView.as_view(), name="pilgrim-detail"),
    path(
        "pilgrims/<uuid:pilgrim_id>/documents",
        views.PilgrimDocumentListCreateView.as_view(),
        name="pilgrim-documents",
    ),
    path(
        "pilgrims/<uuid:pilgrim_id>/documents/<uuid:document_id>",
        views.PilgrimDocumentReviewView.as_view(),
        name="pilgrim-document-review",
    ),
]
