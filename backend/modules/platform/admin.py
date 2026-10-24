from django.contrib import admin

from modules.platform.models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "email", "topic", "created_at", "resolved_at"]
    list_filter = ["topic", "resolved_at"]
    search_fields = ["name", "email", "company"]
    readonly_fields = ["id", "consented_at", "created_at"]
