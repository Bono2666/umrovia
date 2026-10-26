"""Midtrans Snap top-up: signed notifications, status API as truth, exactly-once credit."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.db import DatabaseError, close_old_connections, connection, connections, transaction
from django.test import Client
from django.utils import timezone

from modules.audit.models import AuditEvent
from modules.billing.models import SaaSCharge
from modules.wallet import midtrans
from modules.wallet.models import GatewayOrder, WalletEvent, WalletLedger, WalletTopup
from modules.wallet.services import platform_tenant_context, reconcile_wallet, sync_gateway_topups

from .test_payments import ok, post
from .test_payments import scenario as scenario
from .test_wallet import settle, topup
from .test_wallet import wallet_setup as wallet_setup

SERVER_KEY = "SB-Mid-server-UNIT-TEST"
NOTIFY = "/api/v1/payments/midtrans/notification"


class FakeMidtrans:
    """Stub for midtrans._request: Snap creation + per-order status API."""

    def __init__(self):
        self.statuses = {}
        self.snap_calls = []
        self.fail_snap = False
        self.unreachable = False

    def __call__(self, method, url, payload=None):
        if self.unreachable:
            raise midtrans.GatewayError("Midtrans tidak dapat dihubungi. Coba lagi beberapa saat.")
        if method == "POST":
            self.snap_calls.append(payload)
            if self.fail_snap:
                return 400, {"error_messages": ["gross_amount invalid"]}
            order = payload["transaction_details"]["order_id"]
            return 201, {"token": f"tok-{order}", "redirect_url": f"https://app.sandbox.midtrans.com/snap/v4/redirection/{order}"}
        order = url.rsplit("/", 2)[-2]
        body = self.statuses.get(order)
        return (200, body) if body else (404, {"status_code": "404", "status_message": "Transaction doesn't exist."})

    def set(self, order, transaction_status, *, gross="100000.00", fraud=None, txn=None, payment_type="bank_transfer"):
        body = {"order_id": order, "status_code": "200" if transaction_status in {"settlement", "capture"} else "201", "transaction_status": transaction_status,
                "gross_amount": gross, "transaction_id": txn or f"mid-{uuid4()}", "payment_type": payment_type}
        if fraud:
            body["fraud_status"] = fraud
        self.statuses[order] = body
        return body


def signed(order, status_code="200", gross="100000.00", **extra):
    signature = hashlib.sha512(f"{order}{status_code}{gross}{SERVER_KEY}".encode()).hexdigest()
    return {"order_id": order, "status_code": status_code, "gross_amount": gross, "signature_key": signature, "transaction_status": "settlement", **extra}


def notify(body):
    # A real gateway has no session, cookie or CSRF token.
    return Client(enforce_csrf_checks=True).post(NOTIFY, body, content_type="application/json")


@pytest.fixture
def gateway(wallet_setup, settings):
    settings.MIDTRANS_SERVER_KEY = SERVER_KEY
    settings.MIDTRANS_IS_PRODUCTION = False
    fake = FakeMidtrans()
    with patch("modules.wallet.midtrans._request", fake):
        wallet_setup["fake"] = fake
        yield wallet_setup


def online(s, amount=100_000, key=None):
    return ok(post(s["client"], "/api/v1/wallet/topups", {"amount_idr": amount, "method": "midtrans"}, key=key))


def balance(s):
    return ok(s["client"].get("/api/v1/wallet"))["balance_idr"]


def test_create_returns_snap_redirect_and_is_idempotent(gateway):
    s = gateway
    summary = ok(s["client"].get("/api/v1/wallet"))
    assert summary["topup_methods"] == {"manual": True, "midtrans": True}
    t = online(s, key="online-1")
    assert t["provider"] == "midtrans" and t["status"] == "CREATED"
    assert t["payment_url"].startswith("https://app.sandbox.midtrans.com/")
    assert online(s, key="online-1")["id"] == t["id"]
    assert len(s["fake"].snap_calls) == 1  # replay never reaches the gateway
    snap = s["fake"].snap_calls[0]
    assert snap["transaction_details"] == {"order_id": f"TOP-{t['id']}", "gross_amount": 100_000}
    assert snap["callbacks"]["finish"].endswith(f"/dashboard/wallet?topup={t['id']}")
    assert post(s["client"], "/api/v1/wallet/topups", {"amount_idr": 100_000}, key="online-1").status_code == 409
    assert GatewayOrder.objects.get().order_id == f"TOP-{t['id']}"
    assert balance(s) == 0  # creation never credits


def test_unconfigured_or_rejected_gateway_creates_nothing(gateway, settings):
    s = gateway
    s["fake"].fail_snap = True
    assert post(s["client"], "/api/v1/wallet/topups", {"amount_idr": 100_000, "method": "midtrans"}).status_code == 502
    s["fake"].fail_snap = False
    settings.MIDTRANS_SERVER_KEY = ""
    assert ok(s["client"].get("/api/v1/wallet"))["topup_methods"]["midtrans"] is False
    assert post(s["client"], "/api/v1/wallet/topups", {"amount_idr": 100_000, "method": "midtrans"}).status_code == 400
    assert post(s["client"], "/api/v1/wallet/topups", {"amount_idr": 100_000, "method": "paypal"}).status_code == 400
    assert WalletTopup.objects.without_tenant_guard().count() == GatewayOrder.objects.count() == 0


def test_signed_settlement_credits_exactly_once(gateway):
    s = gateway
    t = online(s)
    order = f"TOP-{t['id']}"
    s["fake"].set(order, "settlement", txn="mid-txn-1")
    for _ in range(4):  # Midtrans retries notifications
        response = notify(signed(order))
        assert response.status_code == 200 and response.json()["status"] == "PAID"
    row = WalletTopup.objects.without_tenant_guard().get()
    assert row.status == "PAID" and row.provider_txn_id == "mid-txn-1" and row.settled_by_id is None
    assert row.gateway_status == "settlement" and row.payment_type == "bank_transfer"
    assert WalletLedger.objects.without_tenant_guard().count() == WalletEvent.objects.without_tenant_guard().count() == 1
    assert balance(s) == 100_000
    assert ok(s["client"].get(f"/api/v1/wallet/topups/{t['id']}"))["payment_url"] is None
    with platform_tenant_context(s["tenant"].pk):
        assert reconcile_wallet().consistent


def test_forged_or_stale_notification_never_credits(gateway):
    s = gateway
    t = online(s)
    order = f"TOP-{t['id']}"
    bad = signed(order)
    bad["signature_key"] = "0" * 128
    assert notify(bad).status_code == 403
    assert notify({"order_id": order}).status_code == 403
    # Valid signature claims settlement, but the status API (truth) says pending.
    s["fake"].set(order, "pending", gross="100000.00")
    assert notify(signed(order)).json()["status"] == "PENDING"
    assert balance(s) == 0 and WalletLedger.objects.without_tenant_guard().count() == 0


def test_amount_mismatch_is_flagged_not_credited(gateway):
    s = gateway
    t = online(s)
    order = f"TOP-{t['id']}"
    s["fake"].set(order, "settlement", gross="10000.00")
    assert notify(signed(order, gross="10000.00")).status_code == 200
    assert WalletTopup.objects.without_tenant_guard().get().status == "PENDING"
    assert balance(s) == 0
    assert AuditEvent.objects.filter(action="wallet.topup.gateway_amount_mismatch").count() == 1


def test_failed_payment_rejects_and_late_settlement_only_alerts(gateway):
    s = gateway
    t = online(s)
    order = f"TOP-{t['id']}"
    s["fake"].set(order, "expire")
    assert notify(signed(order, status_code="407")).json()["status"] == "REJECTED"
    row = WalletTopup.objects.without_tenant_guard().get()
    assert row.status == "REJECTED" and "expire" in row.reason
    s["fake"].set(order, "settlement")
    assert notify(signed(order)).json()["status"] == "REJECTED"
    assert balance(s) == 0
    assert AuditEvent.objects.filter(action="wallet.topup.gateway_conflict").count() == 1


def test_refund_after_paid_requires_review_without_auto_debit(gateway):
    s = gateway
    t = online(s)
    order = f"TOP-{t['id']}"
    s["fake"].set(order, "settlement")
    notify(signed(order))
    s["fake"].set(order, "refund")
    assert notify(signed(order)).json()["status"] == "PAID"
    assert balance(s) == 100_000
    assert AuditEvent.objects.filter(action="wallet.topup.gateway_refunded").count() == 1


def test_unknown_order_acknowledged_and_unreachable_status_retries(gateway):
    s = gateway
    response = notify(signed("payment_notif_test_G123"))
    assert response.status_code == 200 and response.json()["status"] is None
    t = online(s)
    s["fake"].unreachable = True
    assert notify(signed(f"TOP-{t['id']}")).status_code == 502  # non-2xx → Midtrans retries
    assert WalletTopup.objects.without_tenant_guard().get().status == "CREATED"


def test_refresh_endpoint_and_manual_only_paths(gateway):
    s = gateway
    t = online(s)
    order = f"TOP-{t['id']}"
    assert ok(post(s["client"], f"/api/v1/wallet/topups/{t['id']}/refresh"))["status"] == "CREATED"  # not paid yet
    s["fake"].set(order, "capture", fraud="challenge")
    assert ok(post(s["client"], f"/api/v1/wallet/topups/{t['id']}/refresh"))["status"] == "PENDING"
    s["fake"].set(order, "capture", fraud="accept")
    assert ok(post(s["client"], f"/api/v1/wallet/topups/{t['id']}/refresh"))["status"] == "PAID"
    assert balance(s) == 100_000
    # Gateway top-ups take no evidence and no manual settlement.
    assert post(s["client"], f"/api/v1/wallet/topups/{t['id']}/submit", {"payment_reference": "x", "evidence_ref": "y"}).status_code == 409
    other = online(s, amount=50_000)
    assert settle(s, other).status_code == 409
    manual = topup(s, submit=False)
    assert post(s["client"], f"/api/v1/wallet/topups/{manual['id']}/refresh").status_code == 400


def test_sync_and_expiry_of_unpaid_orders(gateway):
    s = gateway
    paid, unpaid = online(s), online(s, amount=50_000)
    s["fake"].set(f"TOP-{paid['id']}", "settlement")
    assert sync_gateway_topups(s["tenant"].pk, older_than=timedelta(0)) == 2
    with platform_tenant_context(s["tenant"].pk):
        assert WalletTopup.objects.get(pk=paid["id"]).status == "PAID"
        assert WalletTopup.objects.get(pk=unpaid["id"]).status == "CREATED"  # no transaction yet, window open
    later = timezone.now() + timedelta(hours=26)
    with patch("modules.wallet.services.timezone.now", return_value=later):
        sync_gateway_topups(s["tenant"].pk, older_than=timedelta(0))
    with platform_tenant_context(s["tenant"].pk):
        assert WalletTopup.objects.get(pk=unpaid["id"]).status == "EXPIRED"


def test_online_topup_settles_pending_saas_charges(gateway, scenario):
    s = gateway
    travel = scenario(environment="production")
    from .test_payments import record

    payment = ok(record(travel, amount=1))
    ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify"))
    assert SaaSCharge.objects.without_tenant_guard().get().status == "PENDING"
    t = online(s)
    s["fake"].set(f"TOP-{t['id']}", "settlement")
    notify(signed(f"TOP-{t['id']}"))
    assert SaaSCharge.objects.without_tenant_guard().get().status == "POSTED"
    assert balance(s) == 50_000


def test_database_guards_for_gateway_rows(gateway):
    s = gateway
    online(s)
    for sql in ["UPDATE wallet_gatewayorder SET order_id = 'TOP-forged'", "DELETE FROM wallet_gatewayorder"]:
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql)
    # A manual top-up still needs a platform officer to become PAID.
    manual = topup(s)
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, TRUE)", [str(s["tenant"].pk)])
        cursor.execute("UPDATE wallet_wallettopup SET status='PAID', paid_at=now(), provider_txn_id='x' WHERE id=%s", [manual["id"]])


def test_signature_helper_rejects_missing_key(settings):
    settings.MIDTRANS_SERVER_KEY = ""
    assert not midtrans.valid_signature(signed("TOP-x"))
    assert midtrans.outcome({"transaction_status": "capture", "fraud_status": "deny"}) == "UNKNOWN"
    assert midtrans.gross_idr("100000.00") == 100_000 and midtrans.gross_idr("10.50") is None


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_notifications_credit_once(gateway):
    s = gateway
    t = online(s)
    order = f"TOP-{t['id']}"
    s["fake"].set(order, "settlement")
    gate = Barrier(5)

    def run(_):
        close_old_connections()
        try:
            gate.wait(timeout=20)
            return notify(signed(order)).status_code
        finally:
            connections.close_all()

    with patch("modules.wallet.midtrans._request", s["fake"]), ThreadPoolExecutor(max_workers=5) as workers:
        statuses = list(workers.map(run, range(5)))
    assert statuses == [200] * 5
    assert WalletLedger.objects.without_tenant_guard().count() == 1
    assert balance(s) == 100_000
