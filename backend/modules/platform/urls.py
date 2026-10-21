from django.urls import path

from modules.platform.views import HealthView

app_name = "platform"

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
]
