from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections, connections
from django.test import Client

from modules.wallet.models import WalletEvent, WalletLedger, WalletTopup
from modules.wallet.services import atomic_debit, platform_tenant_context, reconcile_wallet

from .test_payment_concurrency import race
from .test_payments import ok
from .test_wallet import settle, topup
from .test_wallet import wallet_setup as wallet_setup

pytestmark = pytest.mark.django_db(transaction=True)


def test_ten_concurrent_create_retries_make_one_topup(wallet_setup):
    s = wallet_setup
    jobs = [("/api/v1/wallet/topups", {"amount_idr": 100_000}, "same-topup") for _ in range(10)]
    results = race(s["client"], jobs)
    assert {status for status, _ in results} == {201}, results
    assert len({body["id"] for _, body in results}) == 1
    assert WalletTopup.objects.without_tenant_guard().count() == 1


def test_ten_concurrent_bank_settlements_credit_once(wallet_setup):
    s = wallet_setup
    t = topup(s)
    url = f"/api/v1/platform/tenants/{s['tenant'].pk}/wallet/topups/{t['id']}/settle"
    body = {"amount_idr": 100_000, "provider_txn_id": "BANK-ONE"}
    results = race(s["platform"], [(url, body, str(uuid4())) for _ in range(10)])
    assert {status for status, _ in results} == {200}, results
    assert len({body["ledger_entry_id"] for _, body in results}) == 1
    assert WalletLedger.objects.without_tenant_guard().count() == WalletEvent.objects.without_tenant_guard().count() == 1


@pytest.mark.parametrize("same_reference", [False, True])
def test_concurrent_debits_never_overdraw_or_duplicate(wallet_setup, same_reference):
    s = wallet_setup
    ok(settle(s, topup(s)))
    gate = Barrier(5)
    reference = uuid4()

    def run(index):
        close_old_connections()
        try:
            gate.wait(timeout=20)
            with platform_tenant_context(s["tenant"].pk):
                entry = atomic_debit(reference_id=reference if same_reference else uuid4(), amount_idr=50_000)
                return str(entry.pk) if entry else None
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(run, range(5)))
    assert len(set(result for result in results if result)) == (1 if same_reference else 2)
    assert sum(result is None for result in results) == (0 if same_reference else 3)
    with platform_tenant_context(s["tenant"].pk):
        reconciliation = reconcile_wallet()
        # Raw debits have no SaaSCharge (S13 flags them); balance chain stays exact.
        assert reconciliation.variance_idr == 0 and reconciliation.details_json["chain_ok"]
        assert reconciliation.details_json["orphan_debits"] == (1 if same_reference else 2)
        assert reconciliation.ledger_balance_idr == (50_000 if same_reference else 0)


def test_platform_context_restored_after_settlement(wallet_setup):
    """Platform actor can belong to another travel without leaking RLS context."""
    from django.db import connection

    from modules.tenants.context import get_current_tenant
    from modules.tenants.models import Role, Tenant, TenantMembership

    s = wallet_setup
    other = Tenant.objects.create(slug="other-platform-workspace", legal_name="Other", display_name="Other")
    role = Role.objects.create(tenant=other, name="Owner", permissions_json=["*"])
    TenantMembership.objects.without_tenant_guard().create(tenant=other, role=role, user=s["billing"], status="ACTIVE")
    t = topup(s)
    ok(settle(s, t))
    assert get_current_tenant() is None
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.tenant_id', true)")
        assert not cursor.fetchone()[0]
    own = Client()
    own.force_login(s["billing"])
    assert own.get(f"/api/v1/wallet/topups/{t['id']}").status_code == 404
