"""Keuangan travel API — /bank-accounts (Spec §5.3, S05)."""
from django.urls import path

from modules.travel_finance import views

app_name = "travel_finance"

urlpatterns = [
    path("bank-accounts", views.BankAccountsListCreateView.as_view(), name="bank-accounts"),
    path(
        "bank-accounts/<uuid:bank_account_id>",
        views.BankAccountDetailView.as_view(),
        name="bank-account-detail",
    ),
    path("expenses", views.ExpenseListCreateView.as_view(), name="expenses"),
    path("expenses/<uuid:expense_id>/void", views.ExpenseVoidView.as_view(), name="expense-void"),
]
