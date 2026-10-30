"""S11: room pricing, invoice snapshots, allocations, verified DP and receipts."""
import hashlib
from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import connection
from django.utils import timezone

from modules.audit.models import AuditEvent
from modules.payments.models import PaymentAllocation, PaymentEvent, TravelPayment, TravelReceipt
from modules.tenants.models import TenantEnvironment, TenantSettings

from .pdf_fonts import assert_poppins_only


def post(client, url, body=None, key=None):
    csrf = client.get("/api/v1/auth/csrf").json()["csrfToken"]
    return client.post(url, body or {}, content_type="application/json", HTTP_X_CSRFTOKEN=csrf, HTTP_IDEMPOTENCY_KEY=key or str(uuid4()))


def patch(client, url, body):
    csrf = client.get("/api/v1/auth/csrf").json()["csrfToken"]
    return client.patch(url, body, content_type="application/json", HTTP_X_CSRFTOKEN=csrf)


def ok(response, statuses=(200, 201)):
    assert response.status_code in statuses, response.content
    return response.json()


@pytest.fixture
def scenario(auth_client, tenant_a):
    def make(environment="demo", issue=True, rooms=True, target=0, maker_checker=False):
        TenantEnvironment.objects.get_or_create(tenant=tenant_a, environment=environment, defaults={"state": "ACTIVE"})
        TenantSettings.objects.update_or_create(tenant=tenant_a, defaults={"rules_json": {"payments": {"dp_policy": "any_positive", "dp_minimum_idr": target, "maker_checker": maker_checker}}})
        prices = [{"room_type": room, "price_idr": price} for room, price in [("QUAD", 28_000_000), ("TRIPLE", 29_000_000), ("DOUBLE", 31_000_000)]]
        package = ok(post(auth_client, "/api/v1/packages", {"name": "Umroh Contoh", "price_idr": 28_000_000, "room_prices": prices if rooms else []}))
        pilgrims = [ok(post(auth_client, "/api/v1/pilgrims", {"name": f"Jamaah {i}"})) for i in range(3)]
        departure = ok(post(auth_client, "/api/v1/departures", {"package": package["id"], "start_at": (timezone.now() + timedelta(days=60)).isoformat(), "city_of_origin": "Jakarta", "seat_capacity": 10}))
        ok(post(auth_client, f"/api/v1/departures/{departure['id']}/transition", {"target": "OPEN"}))
        body = {"departure": departure["id"], "participants": [p["id"] for p in pilgrims]}
        if rooms:
            body["room_types"] = {p["id"]: r for p, r in zip(pilgrims, ["QUAD", "TRIPLE", "DOUBLE"], strict=True)}
        booking = ok(post(auth_client, "/api/v1/bookings", body))
        booking = ok(post(auth_client, f"/api/v1/bookings/{booking['id']}/transition", {"target": "RESERVED"}))
        invoice = ok(post(auth_client, f"/api/v1/bookings/{booking['id']}/issue-invoice")) if issue else None
        return {"client": auth_client, "tenant": tenant_a, "package": package, "pilgrims": pilgrims, "departure": departure, "booking": booking, "invoice": invoice, "environment": environment}
    return make


def record(s, amount=1_000_000, participant_index=0, **extra):
    body = {
        "invoice": s["invoice"]["id"], "amount_idr": amount, "kind": "DP", "method": "CASH",
        "received_at": timezone.now().isoformat(), "reference": f"REF-{uuid4().hex[:12]}",
        "allocations": [{"booking_participant_id": s["invoice"]["lines"][participant_index]["participant_id"], "amount_idr": amount}],
        "simulate": s["environment"] == "demo",
        **extra,
    }
    return post(s["client"], "/api/v1/payments", body)


def test_room_prices_mixed_booking_and_frozen_invoice(scenario):
    s = scenario(issue=False)
    assert s["booking"]["total_amount"] == 88_000_000
    assert len(s["booking"]["price_lines"]) == 3
    ok(patch(s["client"], f"/api/v1/packages/{s['package']['id']}", {"room_prices": [{"room_type": "QUAD", "price_idr": 40_000_000}]}))
    # INV-01: invoice sudah terbit otomatis saat reservasi; tombol terbitkan idempoten.
    invoice = ok(post(s["client"], f"/api/v1/bookings/{s['booking']['id']}/issue-invoice"))
    assert invoice["total_idr"] == 88_000_000 and invoice["version"] == 1
    assert invoice["buyer_name"] == "Jamaah 0"
    assert post(s["client"], f"/api/v1/bookings/{s['booking']['id']}/issue-invoice", {"buyer_name": "Keluarga Contoh"}).status_code == 409
    invoice = ok(post(s["client"], f"/api/v1/invoices/{invoice['id']}/revise", {"buyer_name": "Keluarga Contoh", "reason": "Pembayar keluarga"}))
    assert invoice["buyer_name"] == "Keluarga Contoh" and invoice["version"] == 2 and invoice["total_idr"] == 88_000_000
    assert [r["version"] for r in invoice["revisions"]] == [1]
    assert {line["room_type"] for line in invoice["lines"]} == {"QUAD", "TRIPLE", "DOUBLE"}
    again = ok(post(s["client"], f"/api/v1/bookings/{s['booking']['id']}/issue-invoice"))
    assert again == {key: value for key, value in invoice.items() if key not in {"revisions", "revisable"}}
    pdf = s["client"].get(f"/api/v1/invoices/{invoice['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    assert_poppins_only(pdf.content)
    assert hashlib.sha256(pdf.content).hexdigest() == invoice["checksum"]
    assert s["client"].get(f"/api/v1/invoices/{invoice['id']}/pdf").content == pdf.content
    assert invoice["invoice_number"].startswith("DEMO-INV-")


@pytest.mark.parametrize("minimum", [0, 5_000_000])
def test_positive_dp_eligible_even_below_optional_minimum(scenario, minimum):
    s = scenario(target=minimum)
    payment = ok(record(s, amount=1))
    invoice = ok(s["client"].get(f"/api/v1/invoices/{s['invoice']['id']}"))
    assert invoice["paid_idr"] == 0  # submitted money is not yet verified
    verified = ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify"))
    assert verified["status"] == "VERIFIED"
    assert verified["receipt"]["status"] == "ISSUED"
    eligible = [p for p in verified["participants"] if p["dp_eligible_at"]]
    assert len(eligible) == 1 and eligible[0]["status"] == "CONFIRMED"
    assert all(p["status"] == "AWAITING_DP" for p in verified["participants"] if not p["dp_eligible_at"])
    invoice = ok(s["client"].get(f"/api/v1/invoices/{s['invoice']['id']}"))
    assert invoice["balance_idr"] == invoice["total_idr"] - 1


def test_production_verified_dp_pending_charge_still_issues_receipt(scenario):
    s = scenario(environment="production", target=5_000_000)
    payment = ok(record(s, amount=1))
    verified = ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify"))
    assert verified["status"] == "VERIFIED" and verified["receipt"]
    assert not verified["receipt"]["receipt_no"].startswith("DEMO-")
    eligible = [p for p in verified["participants"] if p["dp_eligible_at"]]
    assert len(eligible) == 1 and eligible[0]["status"] == "DP_VERIFIED_PENDING_CHARGE"
    assert eligible[0]["saas_charge_state"] == "pending_charge"
    blocked = post(s["client"], f"/api/v1/bookings/{s['booking']['id']}/transition", {"target": "CONFIRMED"})
    assert blocked.status_code == 400
    assert PaymentEvent.objects.without_tenant_guard().get(kind="payment.verified").payload_json["eligible_participant_ids"] == [eligible[0]["id"]]


def test_verification_idempotency_and_exactly_one_receipt(scenario):
    s = scenario()
    payment = ok(record(s))
    url = f"/api/v1/payments/{payment['id']}/verify"
    first = ok(post(s["client"], url, {"verification_note": "Cocok"}, key="verify-once"))
    for _ in range(5):
        assert ok(post(s["client"], url, {"verification_note": "Cocok"}, key="verify-once")) == first
    assert ok(post(s["client"], url, {}, key="verify-again"))["receipt"]["id"] == first["receipt"]["id"]
    assert post(s["client"], url, {"verification_note": "Berbeda"}, key="verify-once").status_code == 409
    assert TravelReceipt.objects.without_tenant_guard().count() == 1
    assert PaymentEvent.objects.without_tenant_guard().count() == 1
    assert AuditEvent.objects.filter(action="payment.verified").count() == 1



def test_receipt_lines_use_payment_kind_label(scenario):
    s = scenario()
    payment = ok(record(s, kind="INSTALLMENT"))
    ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify"))
    lines = TravelReceipt.objects.without_tenant_guard().get().snapshot_json["lines"]
    assert lines[0]["description"].endswith(" · Cicilan")


def test_payment_limits_and_trace_validation(scenario):
    s = scenario()
    assert record(s, amount=99_000_000).status_code == 400
    assert record(s, amount=0).status_code == 400
    assert record(s, reference="", evidence_ref="").status_code == 400
    assert record(s, simulate=False).status_code == 400
    assert record(s, method="TRANSFER").status_code == 400
    assert TravelPayment.objects.without_tenant_guard().count() == 0
    assert PaymentAllocation.objects.without_tenant_guard().count() == 0


@pytest.mark.parametrize("table", ["catalog_packageroomprice", "payments_travelinvoice", "payments_invoiceline", "payments_travelpayment", "payments_paymentallocation", "payments_travelreceipt", "payments_paymentevent", "payments_paymentoperation", "payments_financialsequence"])
def test_financial_tables_enforce_rls(db, table):
    with connection.cursor() as cursor:
        cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=%s", [table])
        assert cursor.fetchone() == (True, True)


def test_pdf_dates_follow_tenant_calendar():
    from modules.payments.pdf import document_date

    assert document_date("2026-10-25T17:30:00+00:00", "Asia/Jakarta", with_time=True) == "26 Oktober 2026 · 00:30 (Asia/Jakarta)"
    assert document_date("2026-11-02") == "2 November 2026"
