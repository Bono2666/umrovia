"""Corrections retain identities, prices, bank history and role boundaries."""
import json

import pytest

from modules.audit.models import AuditEvent
from modules.departures.models import Departure
from modules.identity import services as identity_services
from modules.pilgrims.models import Pilgrim
from modules.tenants.models import Role, TenantEnvironment
from modules.tenants.rbac import DEFAULT_ROLE_PERMISSIONS
from modules.travel_finance.models import TravelBankAccount

from .test_payments import ok, patch, post, record
from .test_payments import scenario as scenario


def test_pilgrim_partial_correction_preserves_or_explicitly_clears_identity(auth_client, tenant_a):
    TenantEnvironment.objects.create(tenant=tenant_a, environment="demo", state="ACTIVE")
    p = ok(post(auth_client, "/api/v1/pilgrims", {"name":"Jamaah Awal", "identity_number":"3175092102900001", "passport_number":"C1234567", "special_needs":"Kursi roda", "passport_issued_at":"2026-01-01", "passport_expires_at":"2031-01-01"}))
    corrected = ok(patch(auth_client, f"/api/v1/pilgrims/{p['id']}", {"name":"Jamaah Dikoreksi", "phone":"08123456789"}))
    assert corrected["name"] == "Jamaah Dikoreksi"
    assert corrected["identity_masked"] == p["identity_masked"]
    assert corrected["passport_masked"] == p["passport_masked"]
    assert corrected["special_needs"] == "Kursi roda"
    assert "3175092102900001" not in json.dumps(corrected)
    assert patch(auth_client, f"/api/v1/pilgrims/{p['id']}", {"passport_expires_at":"2025-01-01"}).status_code == 400
    cleared = ok(patch(auth_client, f"/api/v1/pilgrims/{p['id']}", {"identity_number":""}))
    assert not cleared["identity_masked"] and cleared["passport_masked"]
    event = AuditEvent.objects.filter(action="pilgrims.updated").latest("occurred_at")
    assert "3175092102900001" not in json.dumps(event.changes_json)


def test_me_exposes_only_active_writable_environments(auth_client, user, tenant_a):
    TenantEnvironment.objects.create(tenant=tenant_a, environment="demo", state="READ_ONLY")
    TenantEnvironment.objects.create(tenant=tenant_a, environment="production", state="ACTIVE")
    me = identity_services.user_payload(user)
    assert me["memberships"][0]["tenant"]["writable_environments"] == ["production"]


def test_bank_number_correctable_before_use_without_leaking_number(auth_client):
    bank = ok(post(auth_client, "/api/v1/bank-accounts", {"bank_name":"Bank Uji", "account_name":"PT Awal", "account_number":"1234567890"}))["bank_account"]
    assert bank["number_editable"]
    corrected = ok(patch(auth_client, f"/api/v1/bank-accounts/{bank['id']}", {"account_name":"PT Koreksi", "account_number":"9876543210"}))["bank_account"]
    assert corrected["account_name"] == "PT Koreksi" and corrected["account_masked"].endswith("3210")
    assert "9876543210" not in json.dumps(corrected)
    assert "9876543210" not in json.dumps(AuditEvent.objects.latest("occurred_at").changes_json)
    listed = ok(auth_client.get("/api/v1/bank-accounts"))["results"]
    assert listed[0]["number_editable"]


def test_used_account_number_locked_but_metadata_correctable(scenario):
    s = scenario()
    bank = ok(post(s["client"], "/api/v1/bank-accounts", {"bank_name":"Bank Uji", "account_name":"PT Awal", "account_number":"1234567890"}))["bank_account"]
    ok(record(s, method="TRANSFER", bank_account=bank["id"]))
    url = f"/api/v1/bank-accounts/{bank['id']}"
    assert patch(s["client"], url, {"account_number":"9876543210"}).status_code == 400
    corrected = ok(patch(s["client"], url, {"account_name":"PT Koreksi", "active":False}))["bank_account"]
    assert corrected["account_masked"] == bank["account_masked"] and not corrected["number_editable"]
    assert not corrected["active"]


def test_bank_duplicate_correction_returns_400_without_side_effects(auth_client):
    for name in ["Bank A", "Bank B"]:
        ok(post(auth_client, "/api/v1/bank-accounts", {"bank_name":name, "account_name":"PT Uji", "account_number":"1234567890"}))
    bank = TravelBankAccount.objects.without_tenant_guard().get(bank_name="Bank B")
    assert patch(auth_client, f"/api/v1/bank-accounts/{bank.pk}", {"bank_name":"Bank A"}).status_code == 400
    bank.refresh_from_db()
    assert bank.bank_name == "Bank B"


def test_departure_package_locked_after_any_booking_and_metadata_editable(scenario):
    s = scenario(issue=False)
    assert s["departure"]["has_bookings"] is False
    current = ok(s["client"].get(f"/api/v1/departures/{s['departure']['id']}"))
    assert current["has_bookings"]
    package = ok(post(s["client"], "/api/v1/packages", {"name":"Paket Berbeda", "price_idr":1}))
    url = f"/api/v1/departures/{current['id']}"
    assert patch(s["client"], url, {"package":package["id"]}).status_code == 400
    corrected = ok(patch(s["client"], url, {"route":"Rute dikoreksi", "meeting_point":"Titik baru", "notes":"Catatan baru"}))
    assert corrected["route"] == "Rute dikoreksi" and corrected["seats_taken"] == 3
    assert patch(s["client"], url, {"seat_capacity":2}).status_code == 400
    assert ok(s["client"].get(url))["seats_taken"] == 3


@pytest.mark.parametrize("status", ["DEPARTED", "COMPLETED", "CANCELED"])
def test_terminal_departure_only_operational_corrections(scenario, status):
    s = scenario(issue=False)
    Departure.objects.without_tenant_guard().filter(pk=s["departure"]["id"]).update(status=status)
    url = f"/api/v1/departures/{s['departure']['id']}"
    assert patch(s["client"], url, {"seat_capacity":100}).status_code == 400
    assert ok(patch(s["client"], url, {"notes":"Koreksi catatan"}))["notes"] == "Koreksi catatan"


def test_draft_correction_preserves_participant_uuid_and_price(scenario):
    # Create a fresh draft on the same open departure, explicitly overriding
    # duplicate registration just for this fixture.
    s = scenario(issue=False)
    booking = ok(post(s["client"], "/api/v1/bookings", {"departure":s["departure"]["id"], "participants":[s["pilgrims"][0]["id"]], "room_types":{s["pilgrims"][0]["id"]:"QUAD"}, "allow_duplicate":True}))
    original = booking["participants"][0]
    ok(patch(s["client"], f"/api/v1/packages/{s['package']['id']}", {"room_prices":[{"room_type":"QUAD", "price_idr":99_000_000}]}))
    corrected = ok(patch(s["client"], f"/api/v1/bookings/{booking['id']}", {"notes":"Catatan dikoreksi"}))
    assert corrected["participants"][0]["id"] == original["id"]
    assert corrected["participants"][0]["pricing_snapshot"] == original["pricing_snapshot"]
    assert corrected["total_amount"] == booking["total_amount"]
    assert patch(s["client"], f"/api/v1/bookings/{s['booking']['id']}", {"notes":"Tidak boleh ubah reservasi"}).status_code == 400


def test_admin_cannot_add_grants_outside_own_scope(auth_client, tenant_a, owner_a):
    target = Role.objects.create(tenant=tenant_a, name="Custom", permissions_json=["bookings.read"])
    owner_a.role = Role.objects.create(tenant=tenant_a, name="Admin", permissions_json=DEFAULT_ROLE_PERMISSIONS["Admin"])
    owner_a.save(update_fields=["role"])
    url = f"/api/v1/roles/{target.pk}"
    assert patch(auth_client, url, {"permissions":["bookings.read", "payments.verify"]}).status_code == 403
    assert post(auth_client, "/api/v1/roles", {"name":"Overreach", "permissions":["wallet.*"]}).status_code == 403
    assert ok(patch(auth_client, url, {"name":"Custom Koreksi", "permissions":[]}))["role"]["permissions"] == []
    target.refresh_from_db()
    assert target.name == "Custom Koreksi"


def test_owner_role_protected_even_if_legacy_system_flag_absent(auth_client, owner_a):
    assert not owner_a.role.is_system
    assert patch(auth_client, f"/api/v1/roles/{owner_a.role_id}", {"permissions":[]}).status_code == 400


def test_correction_foreign_tenant_or_reader_denied(auth_client, owner_a, tenant_a, tenant_b):
    foreign = Pilgrim.objects.without_tenant_guard().create(tenant=tenant_b, environment="production", code="JM-FOREIGN", name="Foreign")
    assert patch(auth_client, f"/api/v1/pilgrims/{foreign.pk}", {"name":"Hacked"}).status_code == 404
    TenantEnvironment.objects.create(tenant=tenant_a, environment="demo", state="ACTIVE")
    own = ok(post(auth_client, "/api/v1/pilgrims", {"name":"Own"}))
    owner_a.role = Role.objects.create(tenant=tenant_a, name="Reader", permissions_json=["pilgrims.read"])
    owner_a.save(update_fields=["role"])
    assert patch(auth_client, f"/api/v1/pilgrims/{own['id']}", {"name":"Hacked"}).status_code == 403
