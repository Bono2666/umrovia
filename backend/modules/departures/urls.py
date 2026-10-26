"""Keberangkatan API — /departures (Spec §8.3, S08)."""
from django.urls import path

from modules.departures import views

app_name = "departures"

urlpatterns = [
    path("departures/staff", views.DepartureStaffView.as_view(), name="departure-staff"),
    path("departures", views.DepartureListCreateView.as_view(), name="departure-list"),
    path("departures/<uuid:departure_id>", views.DepartureDetailView.as_view(), name="departure-detail"),
    path(
        "departures/<uuid:departure_id>/transition",
        views.DepartureTransitionView.as_view(),
        name="departure-transition",
    ),
]
