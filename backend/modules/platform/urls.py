from django.urls import path

from modules.platform import api
from modules.platform.views import ContactMessageView, HealthView

app_name = "platform"

urlpatterns = [
    path("contact", ContactMessageView.as_view(), name="contact"),
    path("health/", HealthView.as_view(), name="health"),
    # S18 konsol platform (staf + MFA)
    path("platform/me", api.PlatformMeView.as_view(), name="platform-me"),
    path("platform/mfa/setup", api.MFASetupView.as_view(), name="platform-mfa-setup"),
    path("platform/mfa/confirm", api.MFAConfirmView.as_view(), name="platform-mfa-confirm"),
    path("platform/mfa/verify", api.MFAVerifyView.as_view(), name="platform-mfa-verify"),
    path("platform/overview", api.OverviewView.as_view(), name="platform-overview"),
    path("platform/tenants", api.TenantListView.as_view(), name="platform-tenants"),
    path("platform/tenants/<uuid:tenant_id>", api.TenantDetailView.as_view(), name="platform-tenant"),
    path("platform/tenants/<uuid:tenant_id>/suspend", api.TenantActionView.as_view(action="suspend"), name="platform-tenant-suspend"),
    path("platform/tenants/<uuid:tenant_id>/reactivate", api.TenantActionView.as_view(action="reactivate"), name="platform-tenant-reactivate"),
    path("platform/tenants/<uuid:tenant_id>/termination", api.TenantActionView.as_view(action="termination"), name="platform-tenant-termination"),
    path("platform/tenants/<uuid:tenant_id>/termination/<uuid:request_id>/decide", api.TerminationDecisionView.as_view(), name="platform-tenant-termination-decide"),
    path("platform/trials", api.TrialListView.as_view(), name="platform-trials"),
    path("platform/trials/<uuid:tenant_id>/extend", api.TrialExtendView.as_view(), name="platform-trial-extend"),
    path("platform/pricing", api.PricingView.as_view(), name="platform-pricing"),
    path("platform/audit", api.AuditView.as_view(), name="platform-audit"),
    path("platform/billing/queue", api.BillingQueueView.as_view(), name="platform-billing-queue"),
    path("platform/support/tickets", api.PlatformTicketListView.as_view(), name="platform-tickets"),
    path("platform/support/tickets/<uuid:ticket_id>", api.PlatformTicketDetailView.as_view(), name="platform-ticket"),
    path("platform/support/tickets/<uuid:ticket_id>/messages", api.PlatformTicketMessageView.as_view(), name="platform-ticket-messages"),
    # Tiket dukungan dari sisi travel
    path("support/tickets", api.SupportTicketListView.as_view(), name="support-tickets"),
    path("support/tickets/<uuid:ticket_id>", api.SupportTicketDetailView.as_view(), name="support-ticket"),
    path("support/tickets/<uuid:ticket_id>/messages", api.SupportTicketMessageView.as_view(), name="support-ticket-messages"),
    path("support/tickets/<uuid:ticket_id>/resolve", api.SupportTicketResolveView.as_view(), name="support-ticket-resolve"),
]
