"""S13 exit gate: exactly-once charge + ledger consistency under real PostgreSQL concurrency."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections, connections
from django.test import Client
from django.utils import timezone

from modules.billing.models import SaaSAdjustment, SaaSCharge
from modules.wallet.models import WalletLedger

from .test_billing import billing as billing
from .test_billing import cancel_booking, charges, fund, pay, reconciled, summary
from .test_payment_concurrency import race
from .test_payments import ok, post
from .test_payments import scenario as scenario
from .test_wallet import topup
from .test_wallet import wallet_setup as wallet_setup

pytestmark = pytest.mark.django_db(transaction=True)


def second_booking(scenario):
    """Three more production participants on a separate booking/invoice."""
    return scenario(environment="production")


def unverified(s, travel, index):
    body = {
        "invoice": travel["invoice"]["id"], "amount_idr": 1_000_000, "kind": "DP", "method": "CASH",
        "received_at": timezone.now().isoformat(), "reference": f"REF-{uuid4().hex[:12]}",
        "allocations": [{"booking_participant_id": travel["invoice"]["lines"][index]["participant_id"], "amount_idr": 1_000_000}],
    }
    return ok(post(travel["client"], "/api/v1/payments", body))


def test_pay02_ten_concurrent_verifications_one_charge(billing):
    s = billing
    fund(s, 100_000)
    payment = pay(s, verify=False)
    url = f"/api/v1/payments/{payment['id']}/verify"
    results = race(s["client"], [(url, {}, f"verify-{i}") for i in range(10)])
    assert {status for status, _ in results} == {200}, results
    assert charges().count() == 1 and charges().get().status == "POSTED"
    assert WalletLedger.objects.without_tenant_guard().filter(kind="DEBIT").count() == 1
    assert summary(s)["balance_idr"] == 50_000
    assert reconciled(s).consistent


def test_pay10_five_charges_funds_for_two(billing, scenario):
    s = billing
    other = second_booking(scenario)
    fund(s, 100_000)
    payments = [unverified(s, s["travel"], i) for i in range(3)] + [unverified(s, other, i) for i in range(2)]
    results = race(s["client"], [(f"/api/v1/payments/{p['id']}/verify", {}, str(uuid4())) for p in payments])
    assert {status for status, _ in results} == {200}, results
    assert charges(status="POSTED").count() == 2 and charges(status="PENDING").count() == 3
    assert summary(s)["balance_idr"] == 0
    result = reconciled(s)
    assert result.consistent and result.details_json["pending_charges"] == 3


def test_topup_settlement_races_verifications_without_deadlock(billing, scenario):
    s = billing
    other = second_booking(scenario)
    pay(s, indices=(0,))  # one older pending charge
    t = topup(s, 150_000)
    payments = [unverified(s, s["travel"], 1), unverified(s, other, 0), unverified(s, other, 1)]
    gate = Barrier(4)

    def settle_job():
        close_old_connections()
        own = Client()
        own.cookies = s["platform"].cookies.copy()
        csrf = own.get("/api/v1/auth/csrf").json()["csrfToken"]
        try:
            gate.wait(timeout=20)
            body = {"amount_idr": 150_000, "provider_txn_id": f"BANK-{t['id']}"}
            response = own.post(f"/api/v1/platform/tenants/{s['tenant'].pk}/wallet/topups/{t['id']}/settle", body, content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
            return response.status_code
        finally:
            connections.close_all()

    def verify_job(payment):
        close_old_connections()
        own = Client()
        own.cookies = s["client"].cookies.copy()
        csrf = own.get("/api/v1/auth/csrf").json()["csrfToken"]
        try:
            gate.wait(timeout=20)
            response = own.post(f"/api/v1/payments/{payment['id']}/verify", {}, content_type="application/json", HTTP_X_CSRFTOKEN=csrf, HTTP_IDEMPOTENCY_KEY=str(uuid4()))
            return response.status_code
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=4) as workers:
        futures = [workers.submit(settle_job)] + [workers.submit(verify_job, p) for p in payments]
        statuses = [f.result(timeout=60) for f in futures]
    assert statuses == [200, 200, 200, 200]
    # 150.000 funds exactly three of the four eligible participants; the oldest is always among them.
    assert charges(status="POSTED").count() == 3 and charges(status="PENDING").count() == 1
    oldest = charges().order_by("eligible_at").first()
    assert oldest.status == "POSTED"
    assert summary(s)["balance_idr"] == 0
    assert reconciled(s).consistent


def test_sec03_concurrent_refund_approvals_credit_once(billing):
    s = billing
    fund(s, 100_000)
    pay(s)
    cancel_booking(s)
    charge = SaaSCharge.objects.without_tenant_guard().get()
    requested = ok(post(s["client"], f"/api/v1/wallet/charges/{charge.pk}/refund-request", {"reason": "Pembatalan disetujui travel"}))
    url = f"/api/v1/platform/tenants/{s['tenant'].pk}/wallet/refunds/{requested['id']}/decide"
    body = {"decision": "APPROVED", "reason": "Sesuai kebijakan"}
    results = race(s["refunds"], [(url, body, str(uuid4())) for _ in range(5)])
    assert {status for status, _ in results} == {200}, results
    assert len({payload["ledger_entry_id"] for _, payload in results}) == 1
    assert WalletLedger.objects.without_tenant_guard().filter(kind="REFUND").count() == 1
    assert SaaSAdjustment.objects.without_tenant_guard().get().status == "APPROVED"
    assert summary(s)["balance_idr"] == 100_000
    assert reconciled(s).consistent


def test_concurrent_retry_requests_never_double_post(billing):
    s = billing
    pay(s, indices=(0, 1, 2))
    fund(s, 100_000)  # posts two oldest; one stays pending
    assert charges(status="PENDING").count() == 1
    results = race(s["client"], [("/api/v1/wallet/charges/retry", {}, str(uuid4())) for _ in range(5)])
    assert {status for status, _ in results} == {200}
    assert sum(body["posted"] for _, body in results) == 0
    assert WalletLedger.objects.without_tenant_guard().filter(kind="DEBIT").count() == 2
    assert reconciled(s).consistent
