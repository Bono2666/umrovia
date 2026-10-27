"""Booking API — /bookings (Spec §8.3, S09)."""
from django.urls import path

from modules.booking import views

app_name = "booking"

urlpatterns = [
    path("bookings", views.BookingListCreateView.as_view(), name="booking-list"),
    path("bookings/<uuid:booking_id>", views.BookingDetailView.as_view(), name="booking-detail"),
    path(
        "bookings/<uuid:booking_id>/transition",
        views.BookingTransitionView.as_view(),
        name="booking-transition",
    ),
    path("waitlist", views.WaitlistListCreateView.as_view(), name="waitlist"),
    path("waitlist/<uuid:entry_id>/book", views.WaitlistActionView.as_view(action="book"), name="waitlist-book"),
    path("waitlist/<uuid:entry_id>/cancel", views.WaitlistActionView.as_view(action="cancel"), name="waitlist-cancel"),
]
