from django.urls import path

from modules.payments import views

app_name = "payments"
urlpatterns = [
    path("invoices", views.InvoiceListView.as_view(), name="invoices"),
    path("invoices/candidates", views.InvoiceCandidatesView.as_view(), name="invoice-candidates"),
    path("invoices/<uuid:invoice_id>", views.InvoiceDetailView.as_view(), name="invoice-detail"),
    path("invoices/<uuid:invoice_id>/pdf", views.InvoicePdfView.as_view(), name="invoice-pdf"),
    path("bookings/<uuid:booking_id>/issue-invoice", views.IssueInvoiceView.as_view(), name="issue-invoice"),
    path("payments", views.PaymentListCreateView.as_view(), name="payments"),
    path("payments/options", views.PaymentOptionsView.as_view(), name="payment-options"),
    path("payments/settings", views.PaymentSettingsView.as_view(), name="payment-settings"),
    path("payments/<uuid:payment_id>", views.PaymentDetailView.as_view(), name="payment-detail"),
    path("payments/<uuid:payment_id>/charge-preview", views.PaymentChargePreviewView.as_view(), name="payment-charge-preview"),
    path("receipts/<uuid:receipt_id>/pdf", views.ReceiptPdfView.as_view(), name="receipt-pdf"),
    *[path(f"payments/<uuid:payment_id>/{action}", views.PaymentActionView.as_view(action=action), name=f"payment-{action}") for action in ["submit", "verify", "reject", "reverse"]],
]
