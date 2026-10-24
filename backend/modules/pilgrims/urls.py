"""Jamaah API — /pilgrims (Spec §8.3, S07)."""
from django.urls import path

from modules.pilgrims import views

app_name = "pilgrims"

urlpatterns = [
    path("pilgrims", views.PilgrimListCreateView.as_view(), name="pilgrim-list"),
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
