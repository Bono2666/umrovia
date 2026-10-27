"""S19: regresi performa — paginasi opt-in dan jumlah query daftar tidak tumbuh per baris (anti N+1)."""
from urllib.parse import urlsplit

from django.db import connection
from django.test.utils import CaptureQueriesContext

from .test_payments import ok, post, record
from .test_payments import scenario as scenario


def queries(client, url):
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200, response.content
    return len(ctx.captured_queries), response.json()


def test_list_endpoints_paginate_on_request(scenario):
    s = scenario(environment="production")
    for index in range(3):
        ok(post(s["client"], f"/api/v1/payments/{ok(record(s, amount=1_000_000, participant_index=index))['id']}/verify"))
    legacy = ok(s["client"].get("/api/v1/payments"))
    assert set(legacy) == {"results"} and len(legacy["results"]) == 3  # klien lama tetap jalan
    page = ok(s["client"].get("/api/v1/payments?page=1&page_size=2"))
    assert page["count"] == 3 and len(page["results"]) == 2 and page["next"] and page["previous"] is None
    following = urlsplit(page["next"])
    assert ok(s["client"].get(f"{following.path}?{following.query}"))["previous"]
    by_invoice = ok(s["client"].get(f"/api/v1/payments?page=1&invoice={s['invoice']['id']}"))
    assert by_invoice["count"] == 3
    bookings = ok(s["client"].get("/api/v1/bookings?page=1&page_size=1"))
    assert bookings["count"] == 1 and len(bookings["results"]) == 1
    assert ok(s["client"].get("/api/v1/invoices?open=1"))["results"][0]["id"] == s["invoice"]["id"]
    number = s["invoice"]["invoice_number"]
    for term in (number, s["booking"]["code"].lower()):
        assert [row["id"] for row in ok(s["client"].get(f"/api/v1/invoices?open=1&q={term}"))["results"]] == [s["invoice"]["id"]]
    assert ok(s["client"].get("/api/v1/invoices?q=tidak-ada"))["results"] == []
    assert s["client"].get("/api/v1/payments?page=99").status_code == 404


def test_list_query_count_does_not_grow_per_row(scenario):
    s = scenario(environment="production")
    ok(post(s["client"], f"/api/v1/payments/{ok(record(s, amount=1_000_000))['id']}/verify"))
    payments_one, _ = queries(s["client"], "/api/v1/payments?page=1")
    invoices_one, _ = queries(s["client"], "/api/v1/invoices?page=1")
    for index in (1, 2):
        ok(post(s["client"], f"/api/v1/payments/{ok(record(s, amount=1_000_000, participant_index=index))['id']}/verify"))
    second = scenario(environment="production")  # booking & invoice kedua
    payments_many, body = queries(s["client"], "/api/v1/payments?page=1")
    invoices_many, invoices = queries(s["client"], "/api/v1/invoices?page=1")
    assert len(body["results"]) == 3 and len(invoices["results"]) == 2 and second["invoice"]
    assert payments_many == payments_one, (payments_one, payments_many)
    assert invoices_many == invoices_one, (invoices_one, invoices_many)
