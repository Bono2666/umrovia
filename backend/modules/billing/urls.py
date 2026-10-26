from django.urls import path

from modules.billing import views

app_name = "billing"
urlpatterns = [
    path("wallet/charges", views.ChargeListView.as_view(), name="charges"),
    path("wallet/charges/retry", views.ChargeRetryView.as_view(), name="charges-retry"),
    path("wallet/charges/<uuid:charge_id>/refund-request", views.RefundRequestView.as_view(), name="refund-request"),
    path("platform/tenants/<uuid:tenant_id>/wallet/refunds", views.PlatformRefundListView.as_view(), name="platform-refunds"),
    path("platform/tenants/<uuid:tenant_id>/wallet/refunds/<uuid:adjustment_id>/decide", views.PlatformRefundDecisionView.as_view(), name="platform-refund-decide"),
]
