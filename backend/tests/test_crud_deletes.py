"""Delete completes CRUD only for unused records; used records keep archive/deactivate/cancel flows."""
import json
from datetime import timedelta

from django.utils import timezone

from modules.audit.models import AuditEvent
from modules.booking.models import Booking, BookingParticipant, BookingPriceLine
from modules.catalog.models import TravelPackage
from modules.departures.models import Departure
from modules.pilgrims.models import Pilgrim
from modules.tenants.models import TenantEnvironment
from modules.travel_finance.models import TravelBankAccount

from .test_payment_security import staff
from .test_payments import ok, post, record
from .test_payments import scenario as scenario


def delete(client, url):
    csrf = client.get("/api/v1/auth/csrf").json()["csrfToken"]
    return client.delete(url, HTTP_X_CSRFTOKEN=csrf)


def guard(model):
    return model.objects.without_tenant_guard()


def demo(tenant):
    TenantEnvironment.objects.get_or_create(tenant=tenant, environment="demo", defaults={"state": "ACTIVE"})


def new_package(client):
    return ok(post(client, "/api/v1/packages", {"name": "Paket Hapus", "price_idr": 25_000_000}))


def new_departure(client, package_id):
    return ok(post(client, "/api/v1/departures", {"package": package_id, "start_at": (timezone.now() + timedelta(days=45)).isoformat(), "city_of_origin": "Surabaya", "seat_capacity": 5}))


def test_unused_records_can_be_deleted_with_audit(auth_client, tenant_a):
    demo(tenant_a)
    pilgrim = ok(post(auth_client, "/api/v1/pilgrims", {"name": "Salah Ketik", "identity_number": "3175092102900009"}))
    assert pilgrim["deletable"]
    assert delete(auth_client, f"/api/v1/pilgrims/{pilgrim['id']}").status_code == 204
    package = new_package(auth_client)
    departure = new_departure(auth_client, package["id"])
    assert departure["deletable"]
    assert not ok(auth_client.get(f"/api/v1/packages/{package['id']}"))["deletable"]
    assert delete(auth_client, f"/api/v1/departures/{departure['id']}").status_code == 204
    assert ok(auth_client.get(f"/api/v1/packages/{package['id']}"))["deletable"]
    assert delete(auth_client, f"/api/v1/packages/{package['id']}").status_code == 204
    bank = ok(post(auth_client, "/api/v1/bank-accounts", {"bank_name": "Bank Hapus", "account_name": "PT Uji", "account_number": "1234567890"}))["bank_account"]
    assert bank["deletable"]
    assert delete(auth_client, f"/api/v1/bank-accounts/{bank['id']}").status_code == 204
    assert not guard(Pilgrim).exists() and not guard(Departure).exists() and not guard(TravelPackage).exists() and not TravelBankAccount.objects.without_tenant_guard().exists()
    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {"pilgrims.deleted", "departures.deleted", "packages.deleted", "bank_accounts.deleted"} <= actions
    pilgrim_event = AuditEvent.objects.get(action="pilgrims.deleted")
    assert "Salah Ketik" not in json.dumps(pilgrim_event.changes_json)
    assert "3175092102900009" not in json.dumps(pilgrim_event.changes_json)
    assert delete(auth_client, f"/api/v1/pilgrims/{pilgrim['id']}").status_code == 404


def test_draft_booking_delete_and_reserved_booking_refused(scenario):
    s = scenario(issue=False)
    reserved = s["booking"]
    assert not reserved["deletable"]
    assert delete(s["client"], f"/api/v1/bookings/{reserved['id']}").status_code == 400
    pilgrim = ok(post(s["client"], "/api/v1/pilgrims", {"name": "Jamaah Draf"}))
    draft = ok(post(s["client"], "/api/v1/bookings", {"departure": s["departure"]["id"], "participants": [pilgrim["id"]], "room_types": {pilgrim["id"]: "QUAD"}}))
    assert draft["deletable"]
    seats = guard(Departure).get(pk=s["departure"]["id"]).seats_taken
    assert delete(s["client"], f"/api/v1/bookings/{draft['id']}").status_code == 204
    assert not guard(Booking).filter(pk=draft["id"]).exists()
    assert not guard(BookingParticipant).filter(booking_id=draft["id"]).exists()
    assert not guard(BookingPriceLine).filter(booking_id=draft["id"]).exists()
    assert guard(Departure).get(pk=s["departure"]["id"]).seats_taken == seats
    # The pilgrim is unused again after the draft disappears.
    assert delete(s["client"], f"/api/v1/pilgrims/{pilgrim['id']}").status_code == 204


def test_used_records_are_refused_with_safe_alternative(scenario):
    s = scenario()
    client = s["client"]
    pilgrim_id = s["pilgrims"][0]["id"]
    for url, expected in [
        (f"/api/v1/pilgrims/{pilgrim_id}", "Arsip"),
        (f"/api/v1/packages/{s['package']['id']}", "Diarsipkan"),
        (f"/api/v1/departures/{s['departure']['id']}", "pembatalan"),
    ]:
        response = delete(client, url)
        assert response.status_code == 400 and expected in response.content.decode(), url
    assert not ok(client.get(f"/api/v1/pilgrims/{pilgrim_id}"))["deletable"]
    assert not ok(client.get(f"/api/v1/departures/{s['departure']['id']}"))["deletable"]
    bank = ok(post(client, "/api/v1/bank-accounts", {"bank_name": "Bank Dipakai", "account_name": "PT Uji", "account_number": "5555666677"}))["bank_account"]
    ok(record(s, method="TRANSFER", bank_account=bank["id"]))
    assert delete(client, f"/api/v1/bank-accounts/{bank['id']}").status_code == 400
    listed = ok(client.get("/api/v1/bank-accounts"))
    rows = listed["bank_accounts"] if "bank_accounts" in listed else listed["results"]
    assert not next(row for row in rows if row["id"] == bank["id"])["deletable"]
    assert guard(Pilgrim).filter(pk=pilgrim_id).exists()


def test_open_departure_without_bookings_is_cancelled_not_deleted(auth_client, tenant_a):
    demo(tenant_a)
    package = new_package(auth_client)
    departure = new_departure(auth_client, package["id"])
    ok(post(auth_client, f"/api/v1/departures/{departure['id']}/transition", {"target": "OPEN"}))
    assert not ok(auth_client.get(f"/api/v1/departures/{departure['id']}"))["deletable"]
    assert delete(auth_client, f"/api/v1/departures/{departure['id']}").status_code == 400


def test_pilgrim_with_document_is_archived_not_deleted(auth_client, tenant_a):
    demo(tenant_a)
    pilgrim = ok(post(auth_client, "/api/v1/pilgrims", {"name": "Punya Dokumen"}))
    prefix = f"tenants/{tenant_a.pk}/environments/demo/pilgrims/{pilgrim['id']}/"
    document = post(auth_client, f"/api/v1/pilgrims/{pilgrim['id']}/documents", {"kind": "passport", "object_key": f"{prefix}paspor.pdf"})
    assert document.status_code in (200, 201), document.content
    assert delete(auth_client, f"/api/v1/pilgrims/{pilgrim['id']}").status_code == 400


def test_delete_permissions_and_read_only_environment(auth_client, tenant_a):
    demo(tenant_a)
    package = new_package(auth_client)
    pilgrim = ok(post(auth_client, "/api/v1/pilgrims", {"name": "Hak Akses"}))
    bank = ok(post(auth_client, "/api/v1/bank-accounts", {"bank_name": "Bank Hak", "account_name": "PT Uji", "account_number": "1111222233"}))["bank_account"]
    sales = staff(tenant_a, "Sales")
    assert delete(sales, f"/api/v1/packages/{package['id']}").status_code == 403
    assert delete(sales, f"/api/v1/bank-accounts/{bank['id']}").status_code == 403
    TenantEnvironment.objects.filter(tenant=tenant_a, environment="demo").update(state="READ_ONLY")
    TenantEnvironment.objects.create(tenant=tenant_a, environment="production", state="ACTIVE")
    assert delete(auth_client, f"/api/v1/pilgrims/{pilgrim['id']}").status_code == 403
    assert delete(auth_client, f"/api/v1/packages/{package['id']}").status_code == 403
    assert guard(Pilgrim).filter(pk=pilgrim["id"]).exists() and guard(TravelPackage).filter(pk=package["id"]).exists()


def test_cross_tenant_delete_is_not_found(auth_client, tenant_a, tenant_b):
    demo(tenant_a)
    TenantEnvironment.objects.create(tenant=tenant_b, environment="demo", state="ACTIVE")
    foreign = Pilgrim.objects.without_tenant_guard().create(tenant=tenant_b, environment="demo", name="Milik Travel Lain", code="JM-FOREIGN1")
    assert delete(auth_client, f"/api/v1/pilgrims/{foreign.pk}").status_code == 404
    assert guard(Pilgrim).filter(pk=foreign.pk).exists()
