from django.urls import path

from modules.reports import views

app_name = "reports"
urlpatterns = [path("reports/<str:kind>", views.ReportView.as_view(), name="report")]
