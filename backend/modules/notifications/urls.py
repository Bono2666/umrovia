from django.urls import path

from modules.notifications import views

app_name = "notifications"
urlpatterns = [
    path("notifications", views.NotificationListView.as_view(), name="list"),
    path("notifications/<uuid:notification_id>", views.NotificationDetailView.as_view(), name="detail"),
    path("notifications/<uuid:notification_id>/resend", views.NotificationResendView.as_view(), name="resend"),
    path("notification-templates", views.TemplateListView.as_view(), name="templates"),
    path("notification-templates/<str:key>", views.TemplateDetailView.as_view(), name="template-detail"),
    path("notification-templates/<str:key>/preview", views.TemplatePreviewView.as_view(), name="template-preview"),
    path("portal/notifications", views.PortalInboxView.as_view(), name="portal-inbox"),
    path("portal/notifications/read-all", views.PortalInboxReadAllView.as_view(), name="portal-inbox-read-all"),
    path("portal/accesses/<uuid:access_id>/notifications/<uuid:notification_id>/read", views.PortalInboxReadView.as_view(), name="portal-inbox-read"),
]
