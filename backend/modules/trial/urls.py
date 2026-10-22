"""Trial API — /trial/* (S04, Spec §8.2)."""
from django.urls import path

from modules.trial import views

app_name = "trial"

urlpatterns = [
    path("trial/status", views.TrialStatusView.as_view(), name="trial-status"),
    path("trial/convert", views.TrialConvertView.as_view(), name="trial-convert"),
    path("trial/demo-bookings", views.TrialDemoBookingsView.as_view(), name="trial-demo-bookings"),
    path("trial/demo-data", views.TrialDemoDataView.as_view(), name="trial-demo-data"),
]
