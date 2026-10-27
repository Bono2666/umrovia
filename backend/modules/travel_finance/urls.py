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
    path("expenses/<uuid:expense_id>/approve", views.ExpenseDecisionView.as_view(action="approve"), name="expense-approve"),
    path("expenses/<uuid:expense_id>/reject", views.ExpenseDecisionView.as_view(action="reject"), name="expense-reject"),
    path("expenses/<uuid:expense_id>/evidence", views.ExpenseEvidenceView.as_view(), name="expense-evidence"),
    path("cash/book", views.CashBookView.as_view(), name="cash-book"),
    path("cash/settings", views.CashSettingsView.as_view(), name="cash-settings"),
    path("cash/opening-balances", views.OpeningBalanceListCreateView.as_view(), name="cash-opening-balances"),
    path("cash/opening-balances/<uuid:balance_id>/approve", views.OpeningBalanceDecisionView.as_view(action="approve"), name="cash-opening-approve"),
    path("cash/opening-balances/<uuid:balance_id>/reject", views.OpeningBalanceDecisionView.as_view(action="reject"), name="cash-opening-reject"),
    path("cash/transfers", views.TransferListCreateView.as_view(), name="cash-transfers"),
    path("cash/transfers/<uuid:transfer_id>/void", views.TransferVoidView.as_view(), name="cash-transfer-void"),
]
