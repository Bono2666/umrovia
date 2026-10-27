from django.urls import path

from modules.agents import views

app_name = "agents"
urlpatterns = [
    path("agents", views.AgentListCreateView.as_view(), name="agents"),
    path("agents/<uuid:agent_id>", views.AgentDetailView.as_view(), name="agent-detail"),
    path("commission-policies", views.PolicyListCreateView.as_view(), name="commission-policies"),
    path("commission-policies/<uuid:policy_id>", views.PolicyDetailView.as_view(), name="commission-policy-detail"),
    path("commissions", views.CommissionListView.as_view(), name="commissions"),
    path("commissions/summary", views.CommissionSummaryView.as_view(), name="commission-summary"),
    *[path(f"commissions/<uuid:commission_id>/{action}", views.CommissionActionView.as_view(action=action), name=f"commission-{action}") for action in ["approve", "pay", "reverse"]],
    path("bookings/<uuid:booking_id>/agent", views.BookingAgentView.as_view(), name="booking-agent"),
]
