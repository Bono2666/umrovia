from django.urls import path

from modules.portal import views

app_name = "portal"
urlpatterns = [
    path("portal/invites/inspect", views.InviteInspectView.as_view(), name="invite-inspect"),
    path("portal/accept-invite", views.AcceptInviteView.as_view(), name="accept-invite"),
    path("portal/me", views.PortalOverviewView.as_view(), name="overview"),
    path("portal/accesses/<uuid:access_id>/documents", views.PortalDocumentsView.as_view(), name="documents"),
    path("portal/accesses/<uuid:access_id>/documents/<uuid:document_id>/download-url", views.PortalDocumentLinkView.as_view(), name="document-link"),
    path("portal/accesses/<uuid:access_id>/profile", views.PortalProfileView.as_view(), name="profile"),
    path("portal/accesses/<uuid:access_id>/change-requests", views.PortalChangeRequestView.as_view(), name="change-requests"),
    path("announcements", views.AnnouncementListCreateView.as_view(), name="announcements"),
    path("announcements/<uuid:announcement_id>", views.AnnouncementDetailView.as_view(), name="announcement-detail"),
    path("pilgrim-change-requests", views.ChangeRequestListView.as_view(), name="pilgrim-change-requests"),
    path("pilgrim-change-requests/<uuid:request_id>/approve", views.ChangeRequestDecisionView.as_view(action="approve"), name="pilgrim-change-approve"),
    path("pilgrim-change-requests/<uuid:request_id>/reject", views.ChangeRequestDecisionView.as_view(action="reject"), name="pilgrim-change-reject"),
    path("portal/accesses/<uuid:access_id>/invoices/<uuid:invoice_id>/pdf", views.PortalInvoicePdfView.as_view(), name="invoice-pdf"),
    path("portal/accesses/<uuid:access_id>/receipts/<uuid:receipt_id>/pdf", views.PortalReceiptPdfView.as_view(), name="receipt-pdf"),
    path("files/pilgrim-documents/<str:token>", views.SignedDocumentFileView.as_view(), name="signed-document"),
    path("pilgrims/<uuid:pilgrim_id>/portal", views.PilgrimPortalView.as_view(), name="pilgrim-portal"),
    path("pilgrims/<uuid:pilgrim_id>/portal/revoke", views.PilgrimPortalRevokeView.as_view(), name="pilgrim-portal-revoke"),
    path("pilgrims/<uuid:pilgrim_id>/documents/upload", views.PilgrimDocumentUploadView.as_view(), name="pilgrim-document-upload"),
    path("pilgrims/<uuid:pilgrim_id>/documents/<uuid:document_id>/download-url", views.PilgrimDocumentLinkView.as_view(), name="pilgrim-document-link"),
]
