from django.contrib import admin

from modules.travel_finance.models import TravelBankAccount


@admin.register(TravelBankAccount)
class TravelBankAccountAdmin(admin.ModelAdmin):
    list_display = ("bank_name", "account_masked", "account_name", "tenant", "active")
    list_filter = ("active", "bank_name")
    search_fields = ("bank_name", "account_name", "tenant__slug")
