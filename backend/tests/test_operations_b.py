"""P0 Tahap B: cabang (MOD-03), daftar tunggu (MOD-06), kas & bank (MOD-11), dashboard KPI (MOD-02)."""
from datetime import timedelta
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.utils import timezone

from modules.audit.models import AuditEvent
from modules.tenants.models import TenantMembership

from .test_payment_security import staff
from .test_payments import ok, post
from .test_payments import patch as http_patch
from .test_payments import scenario as scenario


@pytest.fixture
def ops(scenario):
    return scenario(issue=False)


def _today(s):
    from modules.payments.dates import tenant_today

    return tenant_today(s["tenant"])


def _pay(s, amount=1_000_000):
    invoice = ok(s["client"].get(f"/api/v1/invoices?booking={s['booking']['id']}"))["results"][0]
    line = invoice["lines"][0]
    payment = ok(post(s["client"], "/api/v1/payments", {
        "invoice": invoice["id"], "amount_idr": amount, "kind": "DP", "method": "CASH", "received_at": timezone.now().isoformat(),
        "reference": f"REF-{uuid4().hex[:10]}", "allocations": [{"booking_participant_id": line["participant_id"], "amount_idr": amount}], "simulate": True,
    }))
    return ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify"))


def test_branches_master_default_and_booking_filter(ops):
    client = ops["client"]
    jkt = ok(post(client, "/api/v1/branches", {"code": "jkt", "name": "Kantor Pusat Jakarta", "manager_name": "H. Ridwan"}))
    bks = ok(post(client, "/api/v1/branches", {"code": "BKS", "name": "Cabang Bekasi"}))
    assert jkt["code"] == "JKT" and post(client, "/api/v1/branches", {"code": "JKT", "name": "Dup"}).status_code == 400
    assert post(client, "/api/v1/branches", {"code": "x", "name": "Pendek"}).status_code == 400
    # cabang default staf → isian awal booking baru
    membership = TenantMembership.objects.without_tenant_guard().filter(tenant=ops["tenant"]).order_by("created_at").first()
    assert ok(post(client, f"/api/v1/memberships/{membership.pk}/branch", {"branch": bks["id"]}))["branch"]["code"] == "BKS"
    pilgrim = ok(post(client, "/api/v1/pilgrims", {"name": "Jamaah Bekasi"}))
    body = {"departure": ops["departure"]["id"], "participants": [pilgrim["id"]], "room_types": {pilgrim["id"]: "QUAD"}}
    booking = ok(post(client, "/api/v1/bookings", body))
    assert booking["branch"]["code"] == "BKS"
    moved = ok(http_patch(client, f"/api/v1/bookings/{booking['id']}", {"branch": jkt["id"]}))
    assert moved["branch"]["code"] == "JKT"
    assert [b["code"] for b in ok(client.get(f"/api/v1/bookings?branch={jkt['id']}"))["results"]] == [booking["code"]]
    ok(http_patch(client, f"/api/v1/branches/{bks['id']}", {"active": False}))
    assert http_patch(client, f"/api/v1/bookings/{booking['id']}", {"branch": bks["id"]}).status_code == 400  # nonaktif
    assert ok(post(client, "/api/v1/bookings", {**body, "allow_duplicate": True}))["branch"] is None  # default nonaktif diabaikan
    sales = staff(ops["tenant"], "Sales")
    assert sales.get("/api/v1/branches").status_code == 200 and post(sales, "/api/v1/branches", {"code": "SBY", "name": "X"}).status_code == 403
    report = ok(client.get(f"/api/v1/reports/sales?branch={jkt['id']}"))
    assert report["filter_labels"]["branch"].startswith("JKT") and len({s["key"]: s for s in report["sections"]}["bookings"]["rows"]) == 0  # masih draf


def test_waitlist_only_when_full_and_fifo_booking(scenario):
    s = scenario(issue=False)
    client = s["client"]
    departure = ok(post(client, "/api/v1/departures", {"package": s["package"]["id"], "start_at": (timezone.now() + timedelta(days=50)).isoformat(), "city_of_origin": "Jakarta", "seat_capacity": 1}))
    ok(post(client, f"/api/v1/departures/{departure['id']}/transition", {"target": "OPEN"}))
    people = [ok(post(client, "/api/v1/pilgrims", {"name": f"Antre {i}"})) for i in range(3)]
    assert post(client, "/api/v1/waitlist", {"departure": departure["id"], "pilgrim": people[1]["id"]}).status_code == 400  # masih ada kursi
    first = ok(post(client, "/api/v1/bookings", {"departure": departure["id"], "participants": [people[0]["id"]], "room_types": {people[0]["id"]: "QUAD"}}))
    ok(post(client, f"/api/v1/bookings/{first['id']}/transition", {"target": "RESERVED"}))
    a = ok(post(client, "/api/v1/waitlist", {"departure": departure["id"], "pilgrim": people[1]["id"], "room_type": "DOUBLE", "notes": "Sekeluarga"}))
    b = ok(post(client, "/api/v1/waitlist", {"departure": departure["id"], "pilgrim": people[2]["id"]}))
    assert (a["position"], b["position"]) == (1, 2)
    assert post(client, "/api/v1/waitlist", {"departure": departure["id"], "pilgrim": people[1]["id"]}).status_code == 400  # ganda
    assert post(client, "/api/v1/waitlist", {"departure": departure["id"], "pilgrim": people[0]["id"]}).status_code == 400  # sudah booking
    assert post(client, f"/api/v1/waitlist/{a['id']}/book").status_code == 400  # kursi belum kosong
    ok(post(client, f"/api/v1/bookings/{first['id']}/transition", {"target": "CANCELED", "reason": "Batal"}))
    assert post(client, f"/api/v1/waitlist/{b['id']}/book").status_code == 400  # posisi 2, kursi 1
    booked = ok(post(client, f"/api/v1/waitlist/{a['id']}/book"))
    assert booked["status"] == "BOOKED" and booked["booking"]["code"].startswith("BK-")
    draft = ok(client.get(f"/api/v1/bookings/{booked['booking']['id']}"))
    assert draft["status"] == "DRAFT" and draft["participants"][0]["pricing_snapshot"]["room_type"] == "DOUBLE"
    rows = ok(client.get(f"/api/v1/waitlist?departure={departure['id']}"))["results"]
    assert [(r["pilgrim"]["name"], r["position"]) for r in rows] == [("Antre 2", 1)]
    assert post(client, f"/api/v1/waitlist/{b['id']}/cancel").status_code == 400  # alasan wajib
    assert ok(post(client, f"/api/v1/waitlist/{b['id']}/cancel", {"reason": "Pindah jadwal"}))["status"] == "CANCELED"
    operational = ok(client.get("/api/v1/reports/operational?from=" + (timezone.localdate()).isoformat() + "&to=" + (timezone.localdate() + timedelta(days=90)).isoformat()))
    assert "waitlist" in [c["key"] for c in operational["sections"][0]["columns"]]


def test_opening_balance_transfers_and_cash_book(ops):
    client, today = ops["client"], _today(ops)
    account = ok(post(client, "/api/v1/bank-accounts", {"bank_name": "BSI", "account_name": "PT Contoh", "account_number": "7001234567"}))["bank_account"]
    first = ok(post(client, "/api/v1/cash/opening-balances", {"bank_account": account["id"], "as_of": today.replace(day=1).isoformat(), "amount_idr": 50_000_000}))
    assert first["status"] == "APPROVED"
    assert post(client, "/api/v1/cash/opening-balances", {"bank_account": account["id"], "as_of": today.isoformat(), "amount_idr": 1}).status_code == 400  # koreksi wajib alasan
    ok(post(client, "/api/v1/cash/opening-balances", {"as_of": today.replace(day=1).isoformat(), "amount_idr": 2_000_000}))  # kas tunai
    _pay(ops, 1_000_000)  # tunai masuk
    transfer = ok(post(client, "/api/v1/cash/transfers", {"transferred_on": today.isoformat(), "to_account": account["id"], "amount_idr": 2_500_000, "description": "Setor tunai ke bank"}))
    assert transfer["from_account"] == "Tunai" and transfer["to_account"].startswith("BSI")
    assert post(client, "/api/v1/cash/transfers", {"transferred_on": today.isoformat(), "amount_idr": 1}).status_code == 400  # asal = tujuan
    book = ok(client.get("/api/v1/cash/book"))
    rows = {r["account"]: r for r in book["rows"]}
    assert rows["Tunai"]["opening_idr"] == 2_000_000 and rows["Tunai"]["transfer_out_idr"] == 2_500_000 and rows["Tunai"]["closing_idr"] == 500_000
    assert rows["BSI ******4567"]["closing_idr"] == 52_500_000 and book["totals"]["closing_idr"] == 53_000_000
    # koreksi saldo awal: menunggu persetujuan, maker-checker aktif → pembuat tidak boleh menyetujui
    correction = ok(post(client, "/api/v1/cash/opening-balances", {"bank_account": account["id"], "as_of": today.replace(day=1).isoformat(), "amount_idr": 60_000_000, "reason": "Salah ketik mutasi awal"}))
    assert correction["status"] == "PENDING"
    assert post(client, "/api/v1/cash/opening-balances", {"bank_account": account["id"], "as_of": today.isoformat(), "amount_idr": 1, "reason": "x"}).status_code == 400
    ok(http_patch(client, "/api/v1/cash/settings", {"maker_checker": True}))
    assert post(client, f"/api/v1/cash/opening-balances/{correction['id']}/approve").status_code == 403
    other_owner = staff(ops["tenant"], "Owner")
    assert ok(post(other_owner, f"/api/v1/cash/opening-balances/{correction['id']}/approve"))["status"] == "APPROVED"
    assert {r["account"]: r for r in ok(client.get("/api/v1/cash/book"))["rows"]}["BSI ******4567"]["closing_idr"] == 62_500_000
    ok(post(client, f"/api/v1/cash/transfers/{transfer['id']}/void", {"reason": "Salah rekening"}))
    finance_report = ok(client.get("/api/v1/reports/finance"))
    assert all(c["ok"] for c in finance_report["checks"]), finance_report["checks"]
    finance = staff(ops["tenant"], "Finance")
    assert post(finance, f"/api/v1/cash/opening-balances/{first['id']}/approve").status_code == 403  # checker = Owner


def test_expense_maker_checker_and_evidence(ops):
    client = ops["client"]
    ok(http_patch(client, "/api/v1/cash/settings", {"maker_checker": True}))
    finance = staff(ops["tenant"], "Finance")
    expense = ok(post(finance, "/api/v1/expenses", {"spent_on": _today(ops).isoformat(), "category": "HOTEL", "amount_idr": 4_000_000, "description": "DP hotel Makkah", "payee": "Hotel Al Safwa"}))
    assert expense["approval_status"] == "PENDING" and expense["payee"] == "Hotel Al Safwa"
    listing = ok(finance.get("/api/v1/expenses"))
    assert listing["total_idr"] == 0 and listing["pending_count"] == 1
    assert {k["key"]: k["value"] for k in ok(client.get("/api/v1/reports/finance"))["kpis"]}["expenses"] == 0
    upload = finance.post(f"/api/v1/expenses/{expense['id']}/evidence", {"file": SimpleUploadedFile("nota.pdf", b"%PDF-1.4 nota hotel", content_type="application/pdf")}, HTTP_X_CSRFTOKEN=finance.get("/api/v1/auth/csrf").json()["csrfToken"])
    assert upload.status_code == 200 and upload.json()["has_evidence"]
    bad = finance.post(f"/api/v1/expenses/{expense['id']}/evidence", {"file": SimpleUploadedFile("x.exe", b"MZ....", content_type="application/pdf")}, HTTP_X_CSRFTOKEN=finance.get("/api/v1/auth/csrf").json()["csrfToken"])
    assert bad.status_code == 400
    evidence = client.get(f"/api/v1/expenses/{expense['id']}/evidence")
    assert evidence.status_code == 200 and evidence.content.startswith(b"%PDF")
    assert post(finance, f"/api/v1/expenses/{expense['id']}/approve").status_code == 403  # tanpa expenses.approve
    assert post(client, f"/api/v1/expenses/{expense['id']}/reject").status_code == 400  # alasan wajib
    approved = ok(post(client, f"/api/v1/expenses/{expense['id']}/approve"))
    assert approved["approval_status"] == "APPROVED" and approved["approved_by_name"]
    assert ok(finance.get("/api/v1/expenses"))["total_idr"] == 4_000_000
    own = ok(post(client, "/api/v1/expenses", {"spent_on": _today(ops).isoformat(), "category": "OFFICE", "amount_idr": 100_000, "description": "ATK"}))
    assert post(client, f"/api/v1/expenses/{own['id']}/approve").status_code == 403  # pencatat ≠ penyetuju
    assert AuditEvent.objects.filter(action="expenses.approved").count() == 1


def test_dashboard_summary_respects_permissions(ops):
    client = ops["client"]
    _pay(ops, 2_000_000)
    data = ok(client.get("/api/v1/dashboard/summary"))
    opsb, fin = data["operations"], data["finance"]
    assert opsb["new_bookings_month"] == 1 and opsb["new_pax_month"] == 3 and opsb["sales_estimate_month_idr"] == 88_000_000
    assert opsb["available_seats"] == 7 and opsb["pilgrims"] == 3
    assert {r["status"]: r["count"] for r in opsb["bookings_by_status"]}["RESERVED"] == 1
    assert fin["receivable_idr"] == 86_000_000 and fin["payments_month_idr"] == 2_000_000
    assert len(data["chart"]) == 12 and data["chart"][-1]["bookings"] == 1 and data["chart"][-1]["payments_idr"] == 2_000_000
    assert data["upcoming"][0]["code"] == ops["departure"]["code"]
    operations = ok(staff(ops["tenant"], "Operations").get("/api/v1/dashboard/summary"))
    assert operations["finance"] is None and operations["operations"] is not None
    reviewer = ok(staff(ops["tenant"], "Document Reviewer").get("/api/v1/dashboard/summary"))
    assert reviewer["finance"] is None and reviewer["chart"] is not None  # bookings.read


def test_tahap_b_tables_have_rls(ops):
    with connection.cursor() as cursor:
        cursor.execute("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(%s)", [["tenants_branch", "booking_waitlistentry", "travel_finance_openingbalance", "travel_finance_cashtransfer"]])
        rows = cursor.fetchall()
    assert len(rows) == 4 and all(r[1] and r[2] for r in rows)
