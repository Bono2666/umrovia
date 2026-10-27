from django.urls import path

from modules.crm import views

app_name = "crm"
urlpatterns = [
    path("leads", views.LeadListCreateView.as_view(), name="leads"),
    path("leads/summary", views.LeadSummaryView.as_view(), name="lead-summary"),
    path("leads/owners", views.LeadOwnersView.as_view(), name="lead-owners"),
    path("leads/<uuid:lead_id>", views.LeadDetailView.as_view(), name="lead-detail"),
    path("leads/<uuid:lead_id>/stage", views.LeadStageView.as_view(), name="lead-stage"),
    path("leads/<uuid:lead_id>/activities", views.LeadActivityView.as_view(), name="lead-activities"),
    path("leads/<uuid:lead_id>/convert", views.LeadConvertView.as_view(), name="lead-convert"),
]
