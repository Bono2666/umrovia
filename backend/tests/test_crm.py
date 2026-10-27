"""CRM & Lead (MOD-19): tahap, aktivitas & follow-up, deduplikasi, konversi ke jamaah, funnel, izin, isolasi."""
from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import connection
from django.utils import timezone

from modules.audit.models import AuditEvent
from modules.crm.models import Lead
from modules.pilgrims.models import Pilgrim
from modules.tenants.models import Role, TenantMembership

from .test_payment_security import staff
from .test_payments import ok, post
from .test_payments import patch as http_patch
from .test_payments import scenario as scenario


@pytest.fixture
def crm(scenario):
    return scenario(environment="production", issue=False)


def new_lead(client, **body):
    return post(client, "/api/v1/leads", {"name": "Hj. Fatimah", "phone": "0812-3456-7890", "source": "WHATSAPP", **body})


def test_create_lead_normalizes_and_detects_duplicates(crm):
    client = crm["client"]
    lead = ok(new_lead(client, email="Fatimah@Contoh.test", interest_package=crm["package"]["id"], interest_departure=crm["departure"]["id"], pax=3))
    assert lead["code"].startswith("LD-") and lead["stage"] == "NEW" and lead["phone"] == "+6281234567890"
    assert lead["email"] == "fatimah@contoh.test" and lead["pax"] == 3 and lead["owner"]["name"]
    assert lead["interest_departure"]["code"] == crm["departure"]["code"] and lead["activities"][0]["body"].startswith("Lead dibuat")
    duplicate = new_lead(client, name="Fatimah (WA kedua)", phone="+62 812 3456 7890")
    assert duplicate.status_code == 400 and duplicate.json()["field_errors"]["duplicates"][0]["leads"][0]["code"] == lead["code"]
    assert ok(new_lead(client, name="Fatimah (WA kedua)", phone="+62 812 3456 7890", allow_duplicate=True))["stage"] == "NEW"
    ok(http_patch(client, f"/api/v1/pilgrims/{crm['pilgrims'][0]['id']}", {"email": "budi@contoh.test"}))
    from_pilgrim = new_lead(client, name="Budi", phone="", email="BUDI@contoh.test")
    assert from_pilgrim.json()["field_errors"]["duplicates"][0]["pilgrims"][0]["id"] == crm["pilgrims"][0]["id"]
    for bad in [{"interest_package": str(uuid4())}, {"owner": str(uuid4())}, {"phone": "123"}, {"pax": 0}, {"source": "TV"}, {"name": ""}]:
        assert new_lead(client, **{"phone": "0899000111", **bad}).status_code == 400, bad
    assert AuditEvent.objects.filter(action="leads.created").count() == 2


def test_stage_rules_activities_and_follow_up(crm):
    client = crm["client"]
    lead = ok(new_lead(client))
    url = f"/api/v1/leads/{lead['id']}"
    contacted = ok(post(client, f"{url}/activities", {"kind": "WHATSAPP", "body": "Kirim brosur paket Desember", "next_follow_up_at": (timezone.now() - timedelta(hours=1)).isoformat()}))
    assert contacted["stage"] == "CONTACTED" and contacted["follow_up_overdue"]  # kontak pertama
    assert ok(client.get("/api/v1/leads?follow_up=overdue"))["results"][0]["id"] == lead["id"]
    assert ok(client.get("/api/v1/leads/summary"))["follow_up_overdue"] == 1
    assert post(client, f"{url}/activities", {"kind": "NOTE"}).status_code == 400
    assert post(client, f"{url}/stage", {"stage": "WON"}).status_code == 400
    assert post(client, f"{url}/stage", {"stage": "LOST"}).status_code == 400
    lost = ok(post(client, f"{url}/stage", {"stage": "LOST", "lost_reason": "Memilih travel lain"}))
    assert lost["lost_reason"] == "Memilih travel lain" and lost["next_follow_up_at"] is None
    assert post(client, f"{url}/activities", {"kind": "CALL", "body": "x", "next_follow_up_at": timezone.now().isoformat()}).status_code == 400
    assert post(client, f"{url}/convert").status_code == 400
    reopened = ok(post(client, f"{url}/stage", {"stage": "QUALIFIED"}))
    assert reopened["stage"] == "QUALIFIED" and reopened["lost_reason"] == ""
    kinds = [a["kind"] for a in reopened["activities"]]
    assert kinds.count("STAGE") == 4 and "WHATSAPP" in kinds
    assert post(client, f"{url}/stage", {"stage": "BOGUS"}).status_code == 400


def test_convert_to_new_or_existing_pilgrim(crm):
    client = crm["client"]
    lead = ok(new_lead(client, email="fatimah@contoh.test", city="Bekasi"))
    converted = ok(post(client, f"/api/v1/leads/{lead['id']}/convert"))
    pilgrim = Pilgrim.objects.without_tenant_guard().get(pk=converted["pilgrim"]["id"])
    assert pilgrim.name == "Hj. Fatimah" and pilgrim.phone == "+6281234567890" and pilgrim.email == "fatimah@contoh.test" and pilgrim.environment == "production"
    assert converted["stage"] == "WON" and converted["converted_pilgrim"]["code"] == pilgrim.code and not converted["deletable"]
    again = ok(post(client, f"/api/v1/leads/{lead['id']}/convert"))
    assert again["pilgrim"]["id"] == converted["pilgrim"]["id"]  # idempoten
    assert post(client, f"/api/v1/leads/{lead['id']}/stage", {"stage": "NEW"}).status_code == 400
    assert client.delete(f"/api/v1/leads/{lead['id']}").status_code == 400
    other = ok(new_lead(client, name="Pak Rahmat", phone="0811111111", allow_duplicate=True))
    linked = ok(post(client, f"/api/v1/leads/{other['id']}/convert", {"pilgrim": crm["pilgrims"][1]["id"]}))
    assert linked["pilgrim"]["id"] == crm["pilgrims"][1]["id"]
    assert post(client, f"/api/v1/leads/{ok(new_lead(client, name='X', phone='0822222222'))['id']}/convert", {"pilgrim": str(uuid4())}).status_code == 400
    summary = ok(client.get("/api/v1/leads/summary"))
    assert {s["stage"]: s["count"] for s in summary["stages"]}["WON"] == 2 and summary["conversion_rate"] == 100.0
    assert summary["sources"][0] == {"source": "WHATSAPP", "label": "WhatsApp", "count": 3, "won": 2}


def test_edit_delete_list_filters_and_pagination(crm):
    client = crm["client"]
    lead = ok(new_lead(client))
    edited = ok(http_patch(client, f"/api/v1/leads/{lead['id']}", {"city": "Depok", "pax": 4, "notes": "Rombongan keluarga"}))
    assert edited["city"] == "Depok" and edited["pax"] == 4 and edited["phone"] == "+6281234567890"
    assert http_patch(client, f"/api/v1/leads/{lead['id']}", {"interest_departure": str(uuid4())}).status_code == 400
    for i in range(3):
        ok(new_lead(client, name=f"Calon {i}", phone=f"081300000{i:02d}", source="INSTAGRAM"))
    assert ok(client.get("/api/v1/leads?source=INSTAGRAM"))["results"][0]["source_label"] == "Instagram"
    assert [r["name"] for r in ok(client.get("/api/v1/leads?q=0813-0000-001"))["results"]] == ["Calon 1"]
    assert len(ok(client.get("/api/v1/leads?q=depok"))["results"]) == 1
    page = ok(client.get("/api/v1/leads?page=1&page_size=2&stage=open"))
    assert page["count"] == 4 and len(page["results"]) == 2
    assert len(ok(client.get("/api/v1/leads?owner=me"))["results"]) == 4
    for bad in ["?stage=X", "?owner=bukan-uuid", "?follow_up=kemarin"]:
        assert client.get(f"/api/v1/leads{bad}").status_code == 400, bad
    assert client.delete(f"/api/v1/leads/{lead['id']}").status_code == 204
    assert client.get(f"/api/v1/leads/{lead['id']}").status_code == 404
    assert AuditEvent.objects.filter(action="leads.deleted").count() == 1


def test_permissions_and_owner_choices(crm):
    tenant = crm["tenant"]
    sales, finance, operations = staff(tenant, "Sales"), staff(tenant, "Finance"), staff(tenant, "Operations")
    lead = ok(new_lead(sales))
    assert sales.get("/api/v1/leads").status_code == 200
    assert finance.get("/api/v1/leads").status_code == 403 and operations.get("/api/v1/leads").status_code == 403
    owners = {row["name"] for row in ok(crm["client"].get("/api/v1/leads/owners"))["results"]}
    assert len(owners) == 2  # Owner + Sales; Finance/Operations tanpa leads.manage
    limited_role = Role.objects.create(tenant=tenant, name="Telemarketing", permissions_json=["leads.manage"])
    limited = staff(tenant, "Sales")
    membership = TenantMembership.objects.without_tenant_guard().filter(tenant=tenant).order_by("-created_at").first()
    membership.role = limited_role
    membership.save(update_fields=["role"])
    assert limited.get("/api/v1/leads").status_code == 200
    assert post(limited, f"/api/v1/leads/{lead['id']}/convert").status_code == 403  # butuh pilgrims.write


def test_tenant_isolation_and_rls(crm, tenant_b):
    lead = ok(new_lead(crm["client"]))
    other = staff(tenant_b, "Owner")
    from modules.tenants.models import TenantEnvironment

    TenantEnvironment.objects.create(tenant=tenant_b, environment="production", state="ACTIVE")
    assert ok(other.get("/api/v1/leads"))["results"] == []
    assert other.get(f"/api/v1/leads/{lead['id']}").status_code == 404
    assert post(other, f"/api/v1/leads/{lead['id']}/convert").status_code == 404
    assert ok(other.get("/api/v1/leads/summary"))["total"] == 0
    with connection.cursor() as cursor:
        cursor.execute("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname IN ('crm_lead', 'crm_leadactivity')")
        assert sorted(cursor.fetchall()) == [("crm_lead", True, True), ("crm_leadactivity", True, True)]
    assert Lead.objects.without_tenant_guard().count() == 1
