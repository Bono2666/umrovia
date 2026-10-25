"""PAY02/INV01: konkurensi sungguhan, tiap worker memakai koneksi PostgreSQL sendiri."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from django.db import close_old_connections, connections
from django.test import Client
from django.utils import timezone

from modules.payments.models import PaymentEvent, TravelInvoice, TravelPayment, TravelReceipt

from .test_payments import ok, record
from .test_payments import scenario as scenario

pytestmark = pytest.mark.django_db(transaction=True)


def race(client, jobs):
    gate = Barrier(len(jobs))
    def run(job):
        close_old_connections()
        own = Client()
        own.cookies = client.cookies.copy()
        csrf = own.get("/api/v1/auth/csrf").json()["csrfToken"]
        try:
            gate.wait(timeout=20)
            url, body, key = job
            response = own.post(url, body, content_type="application/json", HTTP_X_CSRFTOKEN=csrf, HTTP_IDEMPOTENCY_KEY=key)
            return response.status_code, response.json()
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=len(jobs)) as workers:
        return list(workers.map(run, jobs))


@pytest.mark.parametrize("same_key", [True, False])
def test_ten_concurrent_verifications_issue_one_receipt(scenario, same_key):
    s = scenario()
    payment = ok(record(s))
    url = f"/api/v1/payments/{payment['id']}/verify"
    results = race(s["client"], [(url, {}, "same-key" if same_key else f"key-{i}") for i in range(10)])
    assert {status for status, _ in results} == {200}, results
    assert len({body["receipt"]["id"] for _, body in results}) == 1
    assert TravelReceipt.objects.without_tenant_guard().count() == 1
    assert PaymentEvent.objects.without_tenant_guard().filter(kind="payment.verified").count() == 1
    invoice = TravelInvoice.objects.without_tenant_guard().get(pk=s["invoice"]["id"])
    assert invoice.balance_idr == invoice.total_idr - 1_000_000


def test_concurrent_invoice_issuance_is_one_document(scenario):
    s = scenario(issue=False)
    url = f"/api/v1/bookings/{s['booking']['id']}/issue-invoice"
    results = race(s["client"], [(url, {}, str(uuid4())) for _ in range(5)])
    assert {status for status, _ in results} == {200}, results
    assert len({body["id"] for _, body in results}) == 1
    assert TravelInvoice.objects.without_tenant_guard().count() == 1


def test_concurrent_recording_cannot_overallocate_participant(scenario):
    s = scenario()
    line = s["invoice"]["lines"][0]
    amount = line["amount_idr"] * 3 // 4
    body = {"invoice": s["invoice"]["id"], "amount_idr": amount, "kind": "DP", "method": "CASH", "received_at": timezone.now().isoformat(), "simulate": True, "allocations": [{"booking_participant_id": line["participant_id"], "amount_idr": amount}]}
    jobs = [("/api/v1/payments", {**body, "reference": f"RACE-{i}"}, str(uuid4())) for i in range(2)]
    results = race(s["client"], jobs)
    assert sorted(status for status, _ in results) == [201, 400], results
    assert TravelPayment.objects.without_tenant_guard().count() == 1
