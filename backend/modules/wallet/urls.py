from django.urls import path

from modules.wallet import views

app_name = "wallet"
urlpatterns = [
    path("wallet", views.WalletView.as_view(), name="summary"),
    path("wallet/ledger", views.LedgerView.as_view(), name="ledger"),
    path("wallet/ledger/export", views.LedgerExportView.as_view(), name="ledger-export"),
    path("wallet/topups", views.TopupListView.as_view(), name="topups"),
    path("wallet/topups/<uuid:topup_id>", views.TopupDetailView.as_view(), name="topup-detail"),
    path("wallet/topups/<uuid:topup_id>/submit", views.TopupSubmitView.as_view(), name="topup-submit"),
    path("wallet/topups/<uuid:topup_id>/evidence", views.TopupEvidenceView.as_view(), name="topup-evidence"),
    path("wallet/topups/<uuid:topup_id>/refresh", views.TopupRefreshView.as_view(), name="topup-refresh"),
    path("payments/midtrans/notification", views.MidtransNotificationView.as_view(), name="midtrans-notification"),
    path("platform/tenants/<uuid:tenant_id>/wallet/topups", views.PlatformTopupListView.as_view(), name="platform-topups"),
    path("platform/tenants/<uuid:tenant_id>/wallet/topups/<uuid:topup_id>/evidence", views.PlatformTopupEvidenceView.as_view(), name="platform-topup-evidence"),
    path("platform/tenants/<uuid:tenant_id>/wallet/topups/<uuid:topup_id>/settle", views.PlatformTopupSettleView.as_view(), name="platform-settle"),
]
