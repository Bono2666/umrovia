"""P0 Tahap C: sesi & audit login (AUTH-02/03/05), pengumuman & koreksi identitas portal (POR-05/06),
keluarga/riwayat/ekspor jamaah (MOD-04), varian harga & layanan tambahan (MOD-05), masa berlaku dokumen (MOD-08)."""
import re
import time
from datetime import date, timedelta

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from modules.audit.models import AuditEvent
from modules.identity.models import User
from modules.pilgrims.models import Pilgrim, PilgrimDocument
from modules.tenants.models import TenantMembership

from .test_payment_security import staff
from .test_payments import ok, post
from .test_payments import patch as http_patch
from .test_payments import scenario as scenario
from .test_portal import portal, private_media, upload  # noqa: F401  (fixture media privat)

PASSWORD = "Rahasia-Staf-2026"


@pytest.fixture
def travel(scenario):
    return scenario(environment="production")


def _login(email, password=PASSWORD):
    client = Client()
    response = post(client, "/api/v1/auth/login", {"email": email, "password": password})
    return client, response


def _staff_user(tenant, role="Sales"):
    staff(tenant, role)
    membership = TenantMembership.objects.without_tenant_guard().filter(tenant=tenant).order_by("-created_at").first()
    membership.user.set_password(PASSWORD)
    membership.user.save()
    return membership


# ------------------------------------------------------------------ AUTH --
def test_login_audit_logout_all_and_absolute_timeout(travel, settings):
    member = _staff_user(travel["tenant"])
    email = member.user.email
    assert _login(email, "salah-sandi")[1].status_code == 401
    assert _login("tidak-ada@example.test", "x")[1].status_code == 401
    first, response = _login(email)
    assert response.status_code == 200
    second, _ = _login(email)
    history = ok(first.get("/api/v1/me/logins"))["results"]
    assert [row["action"] for row in history][:3] == ["auth.login", "auth.login", "auth.login_failed"]
    assert history[2]["reason"] == "invalid_credentials"
    assert AuditEvent.objects.filter(action="auth.login_failed", object_id="").exists()  # email tak dikenal tetap diaudit
    ok(post(second, "/api/v1/auth/logout-all"))
    assert first.get("/api/v1/me").status_code in (401, 403)  # sesi perangkat lain berakhir
    third, _ = _login(email)
    assert third.get("/api/v1/me").status_code == 200
    settings.SESSION_ABSOLUTE_SECONDS = 1
    time.sleep(2.1)
    assert third.get("/api/v1/me").status_code in (401, 403)  # batas absolut


def test_owner_suspends_resets_and_revokes_member_sessions(travel):
    owner = travel["client"]
    member = _staff_user(travel["tenant"])
    session, _ = _login(member.user.email)
    assert session.get("/api/v1/bookings").status_code == 200
    ok(post(owner, f"/api/v1/memberships/{member.pk}/suspend"))
    assert session.get("/api/v1/bookings").status_code == 403  # membership ditangguhkan
    assert post(owner, f"/api/v1/memberships/{member.pk}/suspend").status_code == 400
    ok(post(owner, f"/api/v1/memberships/{member.pk}/reactivate"))
    assert session.get("/api/v1/bookings").status_code == 200
    mail.outbox.clear()
    ok(post(owner, f"/api/v1/memberships/{member.pk}/reset-password"))
    assert mail.outbox and re.search(r"token=", mail.outbox[-1].body)
    ok(post(owner, f"/api/v1/memberships/{member.pk}/revoke-sessions"))
    assert session.get("/api/v1/bookings").status_code in (401, 403)
    actions = [row["action"] for row in ok(owner.get(f"/api/v1/memberships/{member.pk}/logins"))["results"]]
    assert actions[:2] == ["auth.sessions_revoked_by_admin", "auth.reset_requested_by_admin"]
    assert post(staff(travel["tenant"], "Admin"), f"/api/v1/memberships/{member.pk}/suspend").status_code == 403  # Owner-only
    own = TenantMembership.objects.without_tenant_guard().filter(tenant=travel["tenant"], role__name="Owner").first()
    assert post(owner, f"/api/v1/memberships/{own.pk}/suspend").status_code == 400


def test_password_reset_ends_existing_sessions(travel):
    member = _staff_user(travel["tenant"])
    session, _ = _login(member.user.email)
    mail.outbox.clear()
    ok(post(Client(), "/api/v1/auth/password/forgot", {"email": member.user.email}))
    token = re.search(r"token=([\w.\-]+)", mail.outbox[-1].body).group(1)
    ok(post(Client(), "/api/v1/auth/password/reset", {"token": token, "password": "Sandi-Baru-2026!"}))
    assert session.get("/api/v1/me").status_code in (401, 403)
    assert _login(member.user.email, "Sandi-Baru-2026!")[1].status_code == 200


# ---------------------------------------------------------------- PORTAL --
def test_announcements_targeting_and_portal_visibility(travel):
    client = travel["client"]
    other = ok(post(client, "/api/v1/departures", {"package": travel["package"]["id"], "start_at": (timezone.now() + timedelta(days=90)).isoformat(), "city_of_origin": "Medan", "seat_capacity": 5}))
    ok(post(client, "/api/v1/announcements", {"title": "Manasik akbar", "body": "Sabtu pukul 08.00 di kantor.", "departure": travel["departure"]["id"]}))
    ok(post(client, "/api/v1/announcements", {"title": "Info umum", "body": "Libur kantor tanggal 1."}))
    ok(post(client, "/api/v1/announcements", {"title": "Rombongan Medan", "body": "Khusus Medan", "departure": other["id"]}))
    draft = ok(post(client, "/api/v1/announcements", {"title": "Draf", "body": "Belum terbit", "publish": False}))
    assert draft["status"] == "DRAFT"
    assert post(client, "/api/v1/announcements", {"title": "x", "body": "y", "expires_at": (timezone.now() - timedelta(hours=1)).isoformat()}).status_code == 400
    portal_client, access_id, me = portal(travel)
    titles = {a["title"] for a in me["announcements"]}
    assert titles == {"Manasik akbar", "Info umum"}
    ok(http_patch(client, f"/api/v1/announcements/{draft['id']}", {"action": "publish"}))
    assert "Draf" in {a["title"] for a in ok(portal_client.get("/api/v1/portal/me"))["results"][0]["announcements"]}
    assert staff(travel["tenant"], "Sales").get("/api/v1/announcements").status_code == 403
    assert staff(travel["tenant"], "Operations").get("/api/v1/announcements").status_code == 200


def test_identity_change_request_encrypted_and_verified_by_staff(travel):
    portal_client, access_id, _ = portal(travel)
    url = f"/api/v1/portal/accesses/{access_id}/change-requests"
    assert post(portal_client, url, {"changes": {"name": "Budi Santoso"}}).status_code == 400  # alasan wajib
    assert post(portal_client, url, {"changes": {"phone": "0811"}, "reason": "x"}).status_code == 400  # bukan identitas
    assert post(portal_client, url, {"changes": {"identity_number": "123"}, "reason": "x"}).status_code == 400  # NIK 16 digit
    created = ok(post(portal_client, url, {"changes": {"name": "Budi Santoso", "identity_number": "3174012345678901"}, "reason": "Nama di KTP berbeda"}))
    assert created["status"] == "PENDING" and {c["field"]: c["value"] for c in created["changes"]}["identity_number"].endswith("8901")
    assert "3174012345678901" not in str(created)
    assert post(portal_client, url, {"changes": {"birth_place": "Bogor"}, "reason": "lagi"}).status_code == 400  # satu permintaan aktif
    client = travel["client"]
    pending = ok(client.get("/api/v1/pilgrim-change-requests"))["results"]
    assert len(pending) == 1 and pending[0]["pilgrim"]["id"] == travel["pilgrims"][0]["id"]
    assert post(client, f"/api/v1/pilgrim-change-requests/{created['id']}/reject").status_code == 400  # alasan wajib
    ok(post(client, f"/api/v1/pilgrim-change-requests/{created['id']}/approve"))
    pilgrim = ok(client.get(f"/api/v1/pilgrims/{travel['pilgrims'][0]['id']}"))
    assert pilgrim["name"] == "Budi Santoso" and pilgrim["identity_masked"].endswith("8901")
    assert ok(portal_client.get("/api/v1/portal/me"))["results"][0]["change_requests"][0]["status"] == "APPROVED"
    assert AuditEvent.objects.filter(action="pilgrims.change_approved").exists()


# ------------------------------------------------------------- JAMAAH --
def test_family_history_and_authorized_export(travel):
    client = travel["client"]
    family = ok(post(client, "/api/v1/families", {"name": "Keluarga Bp. Ahmad"}))
    a, b = travel["pilgrims"][0]["id"], travel["pilgrims"][1]["id"]
    ok(post(client, f"/api/v1/families/{family['id']}/members", {"pilgrim": a, "relation": "Kepala keluarga"}))
    data = ok(post(client, f"/api/v1/families/{family['id']}/members", {"pilgrim": b, "relation": "Istri"}))
    assert [m["relation"] for m in data["members"]] == ["Kepala keluarga", "Istri"]
    assert post(client, f"/api/v1/families/{family['id']}/members", {"pilgrim": b, "relation": "Kepala keluarga"}).status_code == 400
    assert post(client, f"/api/v1/families/{family['id']}/members", {"pilgrim": b, "relation": "Sepupu jauh"}).status_code == 400
    assert ok(client.get(f"/api/v1/pilgrims?family={family['id']}"))["results"][0]["family"]["name"] == "Keluarga Bp. Ahmad"
    history = ok(client.get(f"/api/v1/pilgrims/{a}/history"))
    assert history["trips"][0]["booking"]["code"] == travel["booking"]["code"] and history["family"]["id"] == family["id"]
    ok(http_patch(client, f"/api/v1/pilgrims/{a}", {"identity_number": "3174012345678901"}))
    csv_masked = client.get("/api/v1/pilgrims/export?file=csv")
    assert csv_masked.status_code == 200 and b"8901" in csv_masked.content and b"3174012345678901" not in csv_masked.content
    full = client.get("/api/v1/pilgrims/export?file=csv&pii=1")
    assert b"3174012345678901" in full.content  # Owner: reports.export_pii
    admin = staff(travel["tenant"], "Admin")
    assert admin.get("/api/v1/pilgrims/export?file=xlsx").status_code == 200
    assert admin.get("/api/v1/pilgrims/export?pii=1").status_code == 400
    assert staff(travel["tenant"], "Sales").get("/api/v1/pilgrims/export").status_code == 403
    assert AuditEvent.objects.filter(action="pilgrims.exported").count() == 3
    ok(client.delete(f"/api/v1/families/{family['id']}/members?pilgrim={b}"), statuses=(200,))


def test_price_variants_addons_flow_to_invoice(scenario):
    s = scenario(issue=False)
    client = s["client"]
    ok(http_patch(client, f"/api/v1/packages/{s['package']['id']}", {
        "child_no_bed_price_idr": 20_000_000, "infant_price_idr": 7_500_000,
        "addons": [{"code": "kereta", "name": "Kereta cepat Makkah–Madinah", "price_idr": 1_200_000}, {"code": "THAIF", "name": "City tour Thaif", "price_idr": 900_000}],
        "estimated_costs": [{"category": "HOTEL", "description": "Hotel Makkah 5 malam", "amount_idr": 9_000_000}, {"category": "TICKET", "description": "Tiket PP", "amount_idr": 12_000_000}],
    }))
    package = ok(client.get(f"/api/v1/packages/{s['package']['id']}"))
    assert package["estimated_cost_per_pax_idr"] == 21_000_000 and package["addons"][0]["code"] == "KERETA"
    baby = ok(post(client, "/api/v1/pilgrims", {"name": "Bayi Aisyah", "birth_date": (date.today() - timedelta(days=300)).isoformat()}))
    kid = ok(post(client, "/api/v1/pilgrims", {"name": "Umar", "birth_date": "2010-01-01"}))
    adult = ok(post(client, "/api/v1/pilgrims", {"name": "Ayah Umar"}))
    body = {"departure": s["departure"]["id"], "participants": [baby["id"], adult["id"]], "room_types": {adult["id"]: "QUAD"},
            "price_categories": {baby["id"]: "INFANT"}, "addons": {adult["id"]: ["KERETA", "THAIF"]}}
    booking = ok(post(client, "/api/v1/bookings", body))
    assert booking["total_amount"] == 7_500_000 + 28_000_000 + 2_100_000
    assert sorted(line["item_type"] for line in booking["price_lines"]) == ["addon", "addon", "package", "package"]
    assert post(client, "/api/v1/bookings", {"departure": s["departure"]["id"], "participants": [kid["id"]], "price_categories": {kid["id"]: "CHILD_NO_BED"}}).status_code == 400  # usia ≥ 12
    assert post(client, "/api/v1/bookings", {**body, "allow_duplicate": True, "addons": {adult["id"]: ["SPA"]}}).status_code == 400
    reserved = ok(post(client, f"/api/v1/bookings/{booking['id']}/transition", {"target": "RESERVED"}))
    invoice = ok(client.get(f"/api/v1/invoices?booking={reserved['id']}"))["results"][0]
    amounts = sorted(line["amount_idr"] for line in invoice["lines"])
    assert amounts == [7_500_000, 30_100_000] and invoice["total_idr"] == 37_600_000
    assert any("Bayi" in line["description"] for line in invoice["lines"]) and any("Kereta cepat" in line["description"] for line in invoice["lines"])
    edited = ok(post(client, "/api/v1/bookings", {"departure": s["departure"]["id"], "participants": [kid["id"]], "allow_duplicate": True, "room_types": {kid["id"]: "QUAD"}}))
    swapped = ok(http_patch(client, f"/api/v1/bookings/{edited['id']}", {"addons": {kid["id"]: ["THAIF"]}}))
    assert swapped["total_amount"] == 28_900_000


def test_document_validity_metadata_and_pilgrim_report(travel):
    client = travel["client"]
    portal_client, access_id, _ = portal(travel)
    doc = ok(upload(portal_client, access_id), statuses=(201,))
    url = f"/api/v1/pilgrims/{travel['pilgrims'][0]['id']}/documents/{doc['id']}"
    expired = http_patch(client, url, {"status": "APPROVED", "expires_at": (date.today() - timedelta(days=1)).isoformat()})
    assert expired.status_code == 400
    assert http_patch(client, url, {"status": "APPROVED", "valid_from": "2026-05-01", "expires_at": "2026-04-01"}).status_code == 400
    soon = (timezone.now() + timedelta(days=30)).date().isoformat()  # sebelum keberangkatan (H+60)
    reviewed = ok(http_patch(client, url, {"status": "APPROVED", "valid_from": "2021-01-10", "expires_at": soon}))
    assert reviewed["expires_at"] == soon and reviewed["expired"] is False
    assert PilgrimDocument.objects.without_tenant_guard().get(pk=doc["id"]).expires_at.isoformat() == soon
    report = ok(client.get(f"/api/v1/reports/pilgrims?from={date.today().isoformat()}&to={(date.today() + timedelta(days=120)).isoformat()}"))
    rows = {r["pilgrim_code"]: r for r in report["sections"][0]["rows"]}
    first = Pilgrim.objects.without_tenant_guard().get(pk=travel["pilgrims"][0]["id"])
    assert rows[first.code]["doc_expiry"] == "Kedaluwarsa sebelum berangkat" and rows[first.code]["readiness"] == "Belum"
    assert {k["key"]: k["value"] for k in report["kpis"]}["pilgrims"] == 3
    assert client.get("/api/v1/reports/pilgrims?file=csv").status_code == 200
    assert User.objects.filter(email__startswith="jamaah").exists()
