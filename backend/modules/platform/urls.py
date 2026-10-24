from django.urls import path

from modules.platform.views import ContactMessageView, HealthView

app_name = "platform"

urlpatterns = [
    path("contact", ContactMessageView.as_view(), name="contact"),
    path("health/", HealthView.as_view(), name="health"),
]
