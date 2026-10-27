"""TBD-08 opsi C (ADR-0019): cakupan cabang per role — staf `OWN` hanya melihat cabangnya + data tanpa cabang."""
from datetime import timedelta

import pytest
from django.utils import timezone

from modules.tenants.models import Role, TenantMembership

from .test_payment_security import staff
from .test_payments import ok, post
from .test_payments import patch as http_patch
from .test_payments import scenario as scenario


def _member(tenant, role_name, scope="OWN"):
    client = staff(tenant, role_name)
    Role.objects.filter(tenant=tenant, name=role_name).update(branch_scope=scope)
    membership = TenantMembership.objects.without_tenant_guard().filter(tenant=tenant).order_by("-created_at").first()
    return client, membership


@pytest.fixture
def world(scenario):
    s = scenario(issue=False)  # booking skenario tanpa cabang (data lama/pusat)
    owner = s["client"]
    s["jkt"] = ok(post(owner, "/api/v1/branches", {"code": "JKT", "name": "Jakarta"}))
    s["sby"] = ok(post(owner, "/api/v1/branches", {"code": "SBY", "name": "Surabaya"}))
    pilgrims = [ok(post(owner, "/api/v1/pilgrims", {"name": f"Peserta {code}"})) for code in ("JKT", "SBY")]
    s["b_jkt"] = ok(post(owner, "/api/v1/bookings", {"departure": s["departure"]["id"], "participants": [pilgrims[0]["id"]], "room_types": {pilgrims[0]["id"]: "QUAD"}, "branch": s["jkt"]["id"]}))
    s["b_sby"] = ok(post(owner, "/api/v1/bookings", {"departure": s["departure"]["id"], "participants": [pilgrims[1]["id"]], "room_types": {pilgrims[1]["id"]: "QUAD"}, "branch": s["sby"]["id"]}))
    for key in ("b_jkt", "b_sby"):
        s[key] = ok(post(owner, f"/api/v1/bookings/{s[key]['id']}/transition", {"target": "RESERVED"}))
    return s


def _assign(owner, membership, *branches, default=None):
    return ok(post(owner, f"/api/v1/memberships/{membership.pk}/branch", {"branches": [b["id"] for b in branches], "branch": default["id"] if default else None}))


def test_own_scope_sees_own_branch_and_unbranched_bookings_only(world):
    owner = world["client"]
    sales, membership = _member(world["tenant"], "Sales")
    assigned = _assign(owner, membership, world["jkt"], default=world["jkt"])
    assert [b["code"] for b in assigned["branches"]] == ["JKT"]
    codes = {b["code"] for b in ok(sales.get("/api/v1/bookings"))["results"]}
    assert codes == {world["booking"]["code"], world["b_jkt"]["code"]}  # + data tanpa cabang
    assert sales.get(f"/api/v1/bookings/{world['b_sby']['id']}").status_code == 404
    assert post(sales, f"/api/v1/bookings/{world['b_sby']['id']}/transition", {"target": "CANCELED", "reason": "x"}).status_code == 404
    # menulis ke cabang lain ditolak; tanpa pilihan → cabang default
    pilgrim = ok(post(sales, "/api/v1/pilgrims", {"name": "Jamaah Sales"}))
    body = {"departure": world["departure"]["id"], "participants": [pilgrim["id"]], "room_types": {pilgrim["id"]: "QUAD"}}
    assert post(sales, "/api/v1/bookings", {**body, "branch": world["sby"]["id"]}).status_code == 403
    assert post(sales, "/api/v1/bookings", {**body, "branch": None}).status_code == 403  # bukan transaksi pusat
    created = ok(post(sales, "/api/v1/bookings", body))
    assert created["branch"]["code"] == "JKT"
    assert http_patch(sales, f"/api/v1/bookings/{created['id']}", {"branch": world["sby"]["id"]}).status_code == 403
    mine = ok(sales.get("/api/v1/branches/mine"))
    assert mine["scope"] == "OWN" and [b["code"] for b in mine["branches"]] == ["JKT"] and mine["default"]["code"] == "JKT"
    # invoice & PDF cabang lain tertutup
    invoices = {i["booking_code"] for i in ok(sales.get("/api/v1/invoices"))["results"]}
    assert world["b_sby"]["code"] not in invoices and world["b_jkt"]["code"] in invoices
    sby_invoice = ok(owner.get(f"/api/v1/invoices?booking={world['b_sby']['id']}"))["results"][0]
    assert sales.get(f"/api/v1/invoices/{sby_invoice['id']}").status_code == 404
    assert sales.get(f"/api/v1/invoices/{sby_invoice['id']}/pdf").status_code == 404
    # Owner tetap melihat semuanya
    assert len(ok(owner.get("/api/v1/bookings"))["results"]) == 4


def test_multi_branch_unassigned_and_no_branch_tenant(world):
    owner = world["client"]
    sales, membership = _member(world["tenant"], "Sales")
    # tanpa penugasan: hanya data tanpa cabang
    assert {b["code"] for b in ok(sales.get("/api/v1/bookings"))["results"]} == {world["booking"]["code"]}
    _assign(owner, membership, world["jkt"], world["sby"])
    assert len(ok(sales.get("/api/v1/bookings"))["results"]) == 3
    # travel tanpa cabang aktif: cakupan tidak berlaku
    _assign(owner, membership)
    for key in ("jkt", "sby"):
        ok(http_patch(owner, f"/api/v1/branches/{world[key]['id']}", {"active": False}))
    assert len(ok(sales.get("/api/v1/bookings"))["results"]) == 3
    assert ok(sales.get("/api/v1/branches/mine"))["scope"] == "ALL"


def test_leads_expenses_and_reports_are_scoped(world):
    owner = world["client"]
    ok(post(owner, "/api/v1/leads", {"name": "Lead SBY", "phone": "081300000001", "branch": world["sby"]["id"]}))
    ok(post(owner, "/api/v1/leads", {"name": "Lead JKT", "phone": "081300000002", "branch": world["jkt"]["id"]}))
    sales, membership = _member(world["tenant"], "Sales")
    _assign(owner, membership, world["jkt"], default=world["jkt"])
    assert [lead["name"] for lead in ok(sales.get("/api/v1/leads"))["results"]] == ["Lead JKT"]
    assert ok(sales.get("/api/v1/leads/summary"))["total"] == 1
    assert ok(post(sales, "/api/v1/leads", {"name": "Lead baru", "phone": "081300000003"}))["branch"]["code"] == "JKT"
    # Operations OWN: laporan & manifest terbatas cabangnya; terbit manifest resmi khusus semua cabang
    ops, ops_membership = _member(world["tenant"], "Operations")
    _assign(owner, ops_membership, world["jkt"], default=world["jkt"])
    report = ok(ops.get("/api/v1/reports/pilgrims?from=" + timezone.localdate().isoformat() + "&to=" + (timezone.localdate() + timedelta(days=120)).isoformat()))
    names = {row["name"] for row in report["sections"][0]["rows"]}
    assert "Peserta JKT" in names and "Peserta SBY" not in names
    assert ops.get(f"/api/v1/reports/pilgrims?branch={world['sby']['id']}").status_code == 403
    manifest = ok(ops.get(f"/api/v1/departures/{world['departure']['id']}/manifest"))
    assert "Peserta SBY" not in {row["name"] for row in manifest["rows"]} and manifest["full_scope"] is False
    assert post(ops, f"/api/v1/departures/{world['departure']['id']}/manifest/publish").status_code == 403
    assert post(owner, f"/api/v1/departures/{world['departure']['id']}/manifest/publish").status_code in (200, 201)
    # Finance OWN (role kustom): pengeluaran per cabang, buku kas & laporan keuangan ditolak
    finance, fin_membership = _member(world["tenant"], "Finance")
    _assign(owner, fin_membership, world["jkt"], default=world["jkt"])
    today = timezone.localdate().isoformat()
    ok(post(owner, "/api/v1/expenses", {"spent_on": today, "category": "OFFICE", "amount_idr": 100_000, "description": "ATK SBY", "branch": world["sby"]["id"]}))
    mine = ok(post(finance, "/api/v1/expenses", {"spent_on": today, "category": "OFFICE", "amount_idr": 50_000, "description": "ATK JKT"}))
    assert mine["branch"]["code"] == "JKT"
    assert [e["description"] for e in ok(finance.get("/api/v1/expenses"))["results"]] == ["ATK JKT"]
    assert finance.get("/api/v1/cash/book").status_code == 403 and finance.get("/api/v1/reports/finance").status_code == 403
    dashboard = ok(finance.get("/api/v1/dashboard/summary"))
    assert dashboard["finance"]["receivable_idr"] == 28_000_000 + 88_000_000  # JKT + booking tanpa cabang


def test_scope_cannot_be_escalated_and_role_api(world):
    owner = world["client"]
    created = ok(post(owner, "/api/v1/roles", {"name": "CS Cabang", "permissions": ["bookings.read"], "branch_scope": "OWN"}))
    assert created["role"]["branch_scope"] == "OWN"
    admin, membership = _member(world["tenant"], "Admin")
    _assign(owner, membership, world["jkt"])
    assert http_patch(admin, f"/api/v1/roles/{created['role']['id']}", {"branch_scope": "ALL"}).status_code == 403
    assert post(admin, "/api/v1/roles", {"name": "Pusat", "permissions": ["bookings.read"], "branch_scope": "ALL"}).status_code == 403
    assert ok(http_patch(owner, f"/api/v1/roles/{created['role']['id']}", {"branch_scope": "ALL"}))["role"]["branch_scope"] == "ALL"
    me = ok(admin.get("/api/v1/me"))
    assert me["memberships"][0]["branch_scope"] == "OWN"
    roles = {r["name"]: r["branch_scope"] for r in ok(owner.get("/api/v1/roles"))["results"]}
    assert roles["Owner"] == "ALL"
