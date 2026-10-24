from django.contrib import admin

from modules.booking.models import Booking, BookingParticipant, BookingPriceLine


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("code", "departure", "status", "environment", "booked_at")
    list_filter = ("environment", "status")
    search_fields = ("code",)
    readonly_fields = ("code", "booked_at", "cancel_reason", "canceled_by", "created_at", "updated_at")


@admin.register(BookingParticipant)
class BookingParticipantAdmin(admin.ModelAdmin):
    list_display = ("booking", "pilgrim", "participant_status", "saas_charge_state", "booking_passenger_id")
    list_filter = ("environment", "participant_status")
    readonly_fields = ("booking_passenger_id", "created_at", "updated_at")


@admin.register(BookingPriceLine)
class BookingPriceLineAdmin(admin.ModelAdmin):
    list_display = ("booking", "item_type", "description", "qty", "unit_price", "amount")
    list_filter = ("environment", "item_type")
    readonly_fields = ("created_at", "updated_at")
