"""P0 Tahap A: invoice otomatis (INV-01), diskon/pembayar & revisi berversi (MOD-07/INV-03), agen & komisi (MOD-10, UAT-09/10)."""
from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import connection
from django.utils import timezone

from modules.agents.models import BookingAgentChange, Commission
from modules.audit.models import AuditEvent
from modules.payments.models import InvoiceLine, TravelInvoiceRevision
from modules.travel_finance.models import TravelExpense

from .test_payment_security import staff
from .test_payments import ok, post
from .test_payments import patch as http_patch
from .test_payments import scenario as scenario


@pytest.fixture
def world(scenario):
    s = scenario(issue=False)
    client = s["client"]
    s["agent"] = ok(post(client, "/api/v1/agents", {"name": "Ust. Hasan", "phone": "0812000111", "bank_name": "BSI", "bank_account_number": "7001234567", "area": "Bekasi"}))
    return s


def _booking(s, *, body=None, reserve=True):
    client = s["client"]
    pilgrims = [ok(post(client, "/api/v1/pilgrims", {"name": f"Peserta {uuid4().hex[:4]}"})) for _ in range(2)]
    payload = {"departure": s["departure"]["id"], "participants": [p["id"] for p in pilgrims], "room_types": {p["id"]: "QUAD" for p in pilgrims}, **(body or {})}
    if callable(payload.get("adjustments")):
        payload["adjustments"] = payload["adjustments"](pilgrims)
    booking = ok(post(client, "/api/v1/bookings", payload))
    if reserve:
        booking = ok(post(client, f"/api/v1/bookings/{booking['id']}/transition", {"target": "RESERVED"}))
    return booking, pilgrims


def _invoice(s, booking):
    rows = ok(s["client"].get(f"/api/v1/invoices?booking={booking['id']}"))["results"]
    assert len(rows) == 1
    return ok(s["client"].get(f"/api/v1/invoices/{rows[0]['id']}"))


def _pay(s, invoice, amount, index=0):
    line = invoice["lines"][index]
    payment = ok(post(s["client"], "/api/v1/payments", {
        "invoice": invoice["id"], "amount_idr": amount, "kind": "DP", "method": "CASH", "received_at": timezone.now().isoformat(),
        "reference": f"REF-{uuid4().hex[:10]}", "allocations": [{"booking_participant_id": line["participant_id"], "amount_idr": amount}], "simulate": True,
    }))
    return ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify"))


def test_reservation_auto_issues_invoice_with_payer_and_discounts(world):
    booking, pilgrims = _booking(world, body={
        "payer_name": "Bp. Ahmad (kantor)",
        "adjustments": lambda ps: {ps[0]["id"]: {"discount_idr": 1_500_000, "note": "Promo early bird"}, ps[1]["id"]: {"extra_idr": 2_000_000, "note": "Upgrade hotel"}},
    })
    assert booking["payer_name"] == "Bp. Ahmad (kantor)" and booking["total_amount"] == 28_000_000 * 2 - 1_500_000 + 2_000_000
    assert [line["item_type"] for line in booking["price_lines"]] == ["package", "adjustment", "adjustment"]
    invoice = _invoice(world, booking)
    assert invoice["buyer_name"] == "Bp. Ahmad (kantor)" and invoice["total_idr"] == 56_500_000
    assert invoice["gross_idr"] == 56_000_000 and invoice["discount_idr"] == 1_500_000 and invoice["extra_idr"] == 2_000_000
    assert {line["amount_idr"] for line in invoice["lines"]} == {26_500_000, 30_000_000} and invoice["revisable"]
    assert any("diskon" in line["description"] and "Promo early bird" in line["description"] for line in invoice["lines"])
    # idempoten: tombol manual mengembalikan invoice yang sama
    assert ok(post(world["client"], f"/api/v1/bookings/{booking['id']}/issue-invoice"))["id"] == invoice["id"]


def test_discount_rules_and_permission(world):
    client = world["client"]
    for bad in [{"discount_idr": 1_000}, {"discount_idr": 28_000_000, "note": "gratis"}, {"discount_idr": -1, "note": "x"}]:
        response = post(client, "/api/v1/bookings", {"departure": world["departure"]["id"], "participants": [world["pilgrims"][0]["id"]], "allow_duplicate": True, "room_types": {world["pilgrims"][0]["id"]: "QUAD"}, "adjustments": {world["pilgrims"][0]["id"]: bad}})
        assert response.status_code == 400, bad
    sales = staff(world["tenant"], "Sales")
    pilgrim = ok(post(sales, "/api/v1/pilgrims", {"name": "Jamaah Sales"}))
    body = {"departure": world["departure"]["id"], "participants": [pilgrim["id"]], "room_types": {pilgrim["id"]: "QUAD"}}
    assert post(sales, "/api/v1/bookings", {**body, "adjustments": {pilgrim["id"]: {"discount_idr": 500_000, "note": "Nego"}}}).status_code == 403
    draft = ok(post(sales, "/api/v1/bookings", {**body, "adjustments": {pilgrim["id"]: {"extra_idr": 750_000, "note": "Kursi lorong"}}}))
    assert draft["total_amount"] == 28_750_000  # biaya tambahan tidak butuh izin diskon
    # ganti kamar saat draf: penyesuaian ikut terbawa
    moved = ok(http_patch(sales, f"/api/v1/bookings/{draft['id']}", {"room_types": {pilgrim["id"]: "DOUBLE"}}))
    assert moved["total_amount"] == 31_750_000 and moved["participants"][0]["pricing_snapshot"]["extra_idr"] == 750_000


def test_invoice_revision_is_versioned_and_blocked_after_payment(world):
    client = world["client"]
    booking, _ = _booking(world)
    invoice = _invoice(world, booking)
    first_checksum, participant = invoice["checksum"], invoice["lines"][0]["participant_id"]
    url = f"/api/v1/invoices/{invoice['id']}/revise"
    assert post(client, url, {"buyer_name": "X"}).status_code == 400  # alasan wajib
    assert post(client, url, {"reason": "tanpa perubahan"}).status_code == 400
    assert post(client, url, {"reason": "x", "adjustments": [{"participant_id": str(uuid4()), "discount_idr": 1, "note": "x"}]}).status_code == 400
    revised = ok(post(client, url, {"reason": "Diskon rombongan disetujui owner", "adjustments": [{"participant_id": participant, "discount_idr": 1_000_000, "note": "Rombongan"}], "due_at": (timezone.localdate() + timedelta(days=20)).isoformat()}))
    assert revised["version"] == 2 and revised["invoice_number"] == invoice["invoice_number"] and revised["total_idr"] == 55_000_000
    assert revised["checksum"] != first_checksum and revised["revision_reason"] == "Diskon rombongan disetujui owner"
    assert revised["revisions"][0]["version"] == 1 and revised["revisions"][0]["total_idr"] == 56_000_000
    old_pdf = client.get(f"/api/v1/invoices/{invoice['id']}/revisions/1/pdf")
    assert old_pdf.status_code == 200 and old_pdf.content.startswith(b"%PDF-")
    assert TravelInvoiceRevision.objects.without_tenant_guard().get(invoice_id=invoice["id"]).checksum == first_checksum
    assert InvoiceLine.objects.without_tenant_guard().filter(invoice_id=invoice["id"]).count() == 2
    assert ok(client.get(f"/api/v1/bookings/{booking['id']}"))["total_amount"] == 55_000_000
    # Sales tanpa invoices.issue tidak dapat merevisi; Admin tanpa bookings.discount tidak dapat mengubah diskon
    assert post(staff(world["tenant"], "Sales"), url, {"reason": "x", "buyer_name": "Y"}).status_code == 403
    _pay(world, revised, 1_000_000)
    blocked = post(client, url, {"reason": "Ganti nama", "buyer_name": "Keluarga"})
    assert blocked.status_code == 400 and "pembayaran" in blocked.json()["field_errors"]["invoice"][0]
    assert AuditEvent.objects.filter(action="invoice.revised").count() == 1


def _policy(s, **body):
    return ok(post(s["client"], "/api/v1/commission-policies", {"name": "Standar", "kind": "FIXED_PER_PAX", "amount_idr": 500_000, **body}))


def test_commission_lifecycle_paid_creates_expense(world):
    client = world["client"]
    _policy(world)
    _policy(world, name="Khusus Hasan", agent=world["agent"]["id"], kind="PERCENT_NET", percent="2.5", amount_idr=0)
    booking, _ = _booking(world, body={"agent": world["agent"]["id"]})
    assert booking["agent"]["code"] == world["agent"]["code"]
    info = ok(client.get(f"/api/v1/bookings/{booking['id']}/agent"))
    commission = info["commission"]
    assert commission["status"] == "ESTIMATED" and commission["policy"]["name"] == "Khusus Hasan"  # kebijakan paling spesifik
    assert commission["basis_idr"] == 56_000_000 and commission["amount_idr"] == 1_400_000 and info["history"][0]["reason"] == "Booking dibuat"
    cid = commission["id"]
    assert post(client, f"/api/v1/commissions/{cid}/approve").status_code == 400  # belum eligible
    # snapshot: mengubah kebijakan tidak mengubah komisi yang ada
    policy_id = commission["policy"]["id"]
    ok(http_patch(client, f"/api/v1/commission-policies/{policy_id}", {"percent": "10"}))
    invoice = _invoice(world, booking)
    _pay(world, invoice, 2_000_000)
    row = ok(client.get(f"/api/v1/commissions?booking={booking['id']}"))["results"][0]
    assert row["status"] == "ELIGIBLE" and row["amount_idr"] == 1_400_000
    assert post(client, f"/api/v1/commissions/{cid}/pay").status_code == 400  # harus disetujui dulu
    assert ok(post(client, f"/api/v1/commissions/{cid}/approve"))["status"] == "APPROVED"
    assert post(client, f"/api/v1/bookings/{booking['id']}/agent", {"agent": None, "reason": "salah input"}).status_code == 400
    paid = ok(post(client, f"/api/v1/commissions/{cid}/pay", {"reference": "TRF-KOM-01"}))
    assert paid["status"] == "PAID" and paid["paid_by"]
    expense = TravelExpense.objects.without_tenant_guard().get(pk=paid["expense_id"])
    assert expense.category == "COMMISSION" and expense.amount_idr == 1_400_000 and expense.departure_id is not None
    summary = {r["status"]: r for r in ok(client.get("/api/v1/commissions/summary"))["statuses"]}
    assert summary["PAID"]["total_idr"] == 1_400_000
    agent = ok(client.get(f"/api/v1/agents/{world['agent']['id']}"))
    assert agent["commission_paid_idr"] == 1_400_000 and agent["booking_count"] == 1 and agent["bank_account_masked"].endswith("4567")
    # pembatalan komisi terbayar (dana kembali) membatalkan kas keluar
    reversed_row = ok(post(client, f"/api/v1/commissions/{cid}/reverse", {"reason": "Agen mengembalikan komisi"}))
    assert reversed_row["status"] == "REVERSED"
    expense.refresh_from_db()
    assert expense.voided_at is not None


def test_cancel_and_agent_change_reverse_commission(world):
    client = world["client"]
    _policy(world, trigger="FULLY_PAID")
    other = ok(post(client, "/api/v1/agents", {"name": "Bu Aminah", "code": "ag-amn"}))
    assert other["code"] == "AG-AMN"
    assert post(client, "/api/v1/agents", {"name": "Dup", "code": "AG-AMN"}).status_code == 400
    booking, _ = _booking(world, body={"agent": world["agent"]["id"]})
    first = Commission.objects.without_tenant_guard().get(booking_id=booking["id"])
    assert first.amount_idr == 1_000_000 and first.policy_snapshot_json["trigger"] == "FULLY_PAID"
    assert post(client, f"/api/v1/bookings/{booking['id']}/agent", {"agent": other["id"]}).status_code == 400  # alasan wajib
    info = ok(post(client, f"/api/v1/bookings/{booking['id']}/agent", {"agent": other["id"], "reason": "Jamaah referensi Bu Aminah"}))
    assert info["agent"]["code"] == "AG-AMN" and info["commission"]["agent"]["code"] == "AG-AMN"
    first.refresh_from_db()
    assert first.status == "REVERSED" and len(info["history"]) == 2
    invoice = _invoice(world, booking)
    _pay(world, invoice, 1_000_000)
    assert ok(client.get(f"/api/v1/commissions?booking={booking['id']}&status=ESTIMATED"))["results"]  # belum lunas
    canceled = ok(post(client, f"/api/v1/bookings/{booking['id']}/transition", {"target": "CANCELED", "reason": "Jamaah sakit"}))
    assert canceled["status"] == "CANCELED"
    statuses = set(Commission.objects.without_tenant_guard().filter(booking_id=booking["id"]).values_list("status", flat=True))
    assert statuses == {"REVERSED"}  # UAT-10
    assert BookingAgentChange.objects.without_tenant_guard().filter(booking_id=booking["id"]).count() == 2


def test_manual_reversal_is_not_recreated_and_no_policy_means_no_commission(world):
    client = world["client"]
    booking, _ = _booking(world, body={"agent": world["agent"]["id"]})
    assert ok(client.get(f"/api/v1/bookings/{booking['id']}/agent"))["commission"] is None  # belum ada kebijakan
    _policy(world)
    booking, _ = _booking(world, body={"agent": world["agent"]["id"]})
    cid = ok(client.get(f"/api/v1/bookings/{booking['id']}/agent"))["commission"]["id"]
    ok(post(client, f"/api/v1/commissions/{cid}/reverse", {"reason": "Agen tidak berhak"}))
    _pay(world, _invoice(world, booking), 500_000)
    assert ok(client.get(f"/api/v1/bookings/{booking['id']}/agent"))["commission"] is None


def test_agent_permissions_and_isolation(world, tenant_b):
    tenant = world["tenant"]
    sales, finance, ops = staff(tenant, "Sales"), staff(tenant, "Finance"), staff(tenant, "Operations")
    assert sales.get("/api/v1/agents").status_code == 200 and post(sales, "/api/v1/agents", {"name": "X"}).status_code == 403
    assert ops.get("/api/v1/agents").status_code == 403
    assert sales.get("/api/v1/commissions").status_code == 403 and finance.get("/api/v1/commissions").status_code == 200
    assert post(finance, "/api/v1/commission-policies", {"name": "F", "kind": "FIXED_PER_PAX", "amount_idr": 1}).status_code == 201
    assert post(finance, "/api/v1/commission-policies", {"name": "F", "kind": "PERCENT_NET"}).status_code == 400
    other = staff(tenant_b, "Owner")
    from modules.tenants.models import TenantEnvironment

    TenantEnvironment.objects.create(tenant=tenant_b, environment="demo", state="ACTIVE")
    assert ok(other.get("/api/v1/agents"))["results"] == []
    assert other.get(f"/api/v1/agents/{world['agent']['id']}").status_code == 404
    with connection.cursor() as cursor:
        cursor.execute("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname LIKE 'agents\\_%%' AND relkind = 'r' OR relname = 'payments_travelinvoicerevision'")
        rows = cursor.fetchall()
    assert len(rows) == 5 and all(r[1] and r[2] for r in rows)


def test_sales_payments_and_commission_reports(world):
    client = world["client"]
    _policy(world)
    booking, _ = _booking(world, body={"agent": world["agent"]["id"], "payer_name": "PT Berkah", "adjustments": lambda ps: {ps[0]["id"]: {"discount_idr": 2_000_000, "note": "Promo"}}})
    direct, _ = _booking(world)
    canceled, _ = _booking(world)
    ok(post(client, f"/api/v1/bookings/{canceled['id']}/transition", {"target": "CANCELED", "reason": "Batal"}))
    _pay(world, _invoice(world, booking), 3_000_000)

    report = ok(client.get("/api/v1/reports/sales"))
    kpis = {k["key"]: k["value"] for k in report["kpis"]}
    # + booking skenario (3 jamaah QUAD/TRIPLE/DOUBLE = Rp88 juta)
    assert kpis["bookings"] == 3 and kpis["gross"] == 88_000_000 + 56_000_000 * 2 and kpis["discount"] == 2_000_000 and kpis["net"] == 198_000_000
    assert all(check["ok"] for check in report["checks"]), report["checks"]
    sections = {s["key"]: s for s in report["sections"]}
    assert {r["agent"]: r["net_idr"] for r in sections["agents"]["rows"]} == {"Ust. Hasan": 54_000_000, "Langsung": 88_000_000 + 56_000_000}
    assert next(r for r in sections["bookings"]["rows"] if r["booking_code"] == canceled["code"])["net_idr"] == 0
    assert next(r for r in sections["bookings"]["rows"] if r["booking_code"] == booking["code"])["payer"] == "PT Berkah"
    by_agent = ok(client.get(f"/api/v1/reports/sales?agent={world['agent']['id']}"))
    assert len({s["key"]: s for s in by_agent["sections"]}["bookings"]["rows"]) == 1 and by_agent["filter_labels"]["agent"] == "Ust. Hasan"
    assert client.get(f"/api/v1/reports/sales?agent={uuid4()}").status_code == 400

    payments = ok(client.get("/api/v1/reports/payments"))
    assert {k["key"]: k["value"] for k in payments["kpis"]}["verified"] == 3_000_000 and all(c["ok"] for c in payments["checks"])
    assert {s["key"]: s for s in payments["sections"]}["accounts"]["rows"][0]["account"] == "Tunai"
    assert ok(client.get("/api/v1/reports/payments?account=CASH"))["filter_labels"]["account"] == "Tunai"

    cid = ok(client.get(f"/api/v1/bookings/{booking['id']}/agent"))["commission"]["id"]
    ok(post(client, f"/api/v1/commissions/{cid}/approve"))
    ok(post(client, f"/api/v1/commissions/{cid}/pay"))
    commissions = ok(client.get("/api/v1/reports/commissions"))
    kpis = {k["key"]: k["value"] for k in commissions["kpis"]}
    assert kpis["earned"] == 1_000_000 and kpis["paid_period"] == 1_000_000 and all(c["ok"] for c in commissions["checks"])
    assert client.get("/api/v1/reports/commissions?file=xlsx").status_code == 200
    sales = staff(world["tenant"], "Sales")
    assert sales.get("/api/v1/reports/commissions").status_code == 403 and sales.get("/api/v1/reports/sales").status_code == 403
    assert staff(world["tenant"], "Finance").get("/api/v1/reports/payments").status_code == 200
