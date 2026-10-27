from django.urls import path

from modules.reports import views

app_name = "reports"
urlpatterns = [
    path("dashboard/summary", views.DashboardSummaryView.as_view(), name="dashboard-summary"),
    path("reports/<str:kind>", views.ReportView.as_view(), name="report"),
]
