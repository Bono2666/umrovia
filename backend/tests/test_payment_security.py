"""S11: permission, correction history, validation and transaction rollback."""
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.utils import timezone

from modules.catalog.models import PackageRoomPrice
from modules.identity.models import User
from modules.payments.models import PaymentEvent, TravelInvoice, TravelPayment, TravelReceipt
from modules.tenants.models import Role, TenantEnvironment, TenantMembership
from modules.tenants.rbac import DEFAULT_ROLE_PERMISSIONS

from .test_payments import ok, patch, post, record
from .test_payments import scenario as scenario


def staff(tenant, name):
    user = User.objects.create_user(email=f"{uuid4().hex}@example.test", status="ACTIVE", email_verified_at=timezone.now())
    role, _ = Role.objects.get_or_create(tenant=tenant, name=name, defaults={"permissions_json": DEFAULT_ROLE_PERMISSIONS[name]})
    TenantMembership.objects.without_tenant_guard().create(tenant=tenant, user=user, role=role, status="ACTIVE")
    client = Client()
    client.force_login(user)
    return client


def test_maker_checker_requires_another_verifier(scenario):
    s = scenario(maker_checker=True)
    payment = ok(record(s, amount=1))
    url = f"/api/v1/payments/{payment['id']}/verify"
    assert post(s["client"], url).status_code == 403
    assert TravelReceipt.objects.without_tenant_guard().count() == 0
    finance = staff(s["tenant"], "Finance")
    assert ok(post(finance, url))["status"] == "VERIFIED"


def test_reversal_preserves_receipt_and_reopens_balance(scenario):
    s = scenario()
    payment = ok(record(s))
    url = f"/api/v1/payments/{payment['id']}"
    verified = ok(post(s["client"], url + "/verify"))
    receipt = verified["receipt"]
    original_pdf = s["client"].get(f"/api/v1/receipts/{receipt['id']}/pdf").content
    assert post(s["client"], url + "/reverse", {"reason": "Koreksi"}).status_code == 403
    finance = staff(s["tenant"], "Finance")
    assert post(finance, url + "/reverse", {}).status_code == 400
    reversed_payment = ok(post(finance, url + "/reverse", {"reason": "Bukti salah"}))
    assert reversed_payment["status"] == "REVERSED"
    assert reversed_payment["receipt"]["id"] == receipt["id"]
    assert reversed_payment["receipt"]["status"] == "REVERSED"
    assert finance.get(f"/api/v1/receipts/{receipt['id']}/pdf").content == original_pdf
    invoice = ok(finance.get(f"/api/v1/invoices/{s['invoice']['id']}"))
    assert invoice["balance_idr"] == invoice["total_idr"]
    assert TravelReceipt.objects.without_tenant_guard().count() == 1
    assert PaymentEvent.objects.without_tenant_guard().filter(kind="payment.reversed").count() == 1


def test_draft_evidence_then_submission_and_rejection(scenario):
    s = scenario()
    draft = ok(record(s, reference="", submit=False))
    assert draft["status"] == "DRAFT"
    url = f"/api/v1/payments/{draft['id']}"
    assert post(s["client"], url + "/submit").status_code == 400
    assert patch(s["client"], url, {"amount_idr": 2}).status_code == 400
    ok(patch(s["client"], url, {"evidence_ref": "Catatan kas contoh"}))
    assert ok(post(s["client"], url + "/submit"))["status"] == "SUBMITTED"
    assert patch(s["client"], url, {"evidence_ref": "Ubah"}).status_code == 400
    assert post(s["client"], url + "/reject").status_code == 400
    assert ok(post(s["client"], url + "/reject", {"reason": "Belum diterima"}))["status"] == "REJECTED"
    assert post(s["client"], url + "/verify").status_code == 400
    assert TravelReceipt.objects.without_tenant_guard().count() == 0


def test_sales_can_record_but_cannot_verify_or_read_another_payment(scenario):
    s = scenario()
    owner_payment = ok(record(s))
    sales = staff(s["tenant"], "Sales")
    assert sales.get(f"/api/v1/payments/{owner_payment['id']}").status_code == 404
    assert post(sales, f"/api/v1/payments/{owner_payment['id']}/verify").status_code == 403
    assert post(sales, f"/api/v1/bookings/{s['booking']['id']}/issue-invoice").status_code == 403
    s["client"] = sales
    own = ok(record(s, participant_index=1))
    assert sales.get(f"/api/v1/payments/{own['id']}").status_code == 200
    admin = staff(s["tenant"], "Admin")
    assert admin.get(f"/api/v1/payments/{own['id']}").status_code == 200
    assert post(admin, f"/api/v1/payments/{own['id']}/verify").status_code == 403
    finance = staff(s["tenant"], "Finance")
    assert ok(post(finance, f"/api/v1/payments/{own['id']}/verify"))["status"] == "VERIFIED"


def test_cross_tenant_financial_objects_denied(scenario, tenant_b):
    s = scenario()
    payment = ok(record(s))
    verified = ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify"))
    foreign = staff(tenant_b, "Owner")
    paths = [f"invoices/{s['invoice']['id']}", f"invoices/{s['invoice']['id']}/pdf", f"payments/{payment['id']}", f"receipts/{verified['receipt']['id']}/pdf"]
    for path in paths:
        assert foreign.get("/api/v1/" + path).status_code == 404
    assert post(foreign, f"/api/v1/payments/{payment['id']}/verify").status_code == 404
    assert post(foreign, f"/api/v1/bookings/{s['booking']['id']}/issue-invoice").status_code == 404


def test_readonly_environment_blocks_financial_writes(scenario):
    s = scenario()
    payment = ok(record(s))
    TenantEnvironment.objects.filter(tenant=s["tenant"], environment="demo").update(state="READ_ONLY")
    assert record(s).status_code == 403
    assert post(s["client"], f"/api/v1/payments/{payment['id']}/verify").status_code == 403
    assert post(s["client"], f"/api/v1/bookings/{s['booking']['id']}/issue-invoice").status_code == 403
    assert s["client"].get(f"/api/v1/invoices/{s['invoice']['id']}/pdf").status_code == 200


def test_allocations_must_match_invoice_and_verification(scenario):
    s = scenario()
    wrong = [{"booking_participant_id": str(uuid4()), "amount_idr": 1_000_000}]
    assert record(s, allocations=wrong).status_code == 400
    partial = [{"booking_participant_id": s["invoice"]["lines"][0]["participant_id"], "amount_idr": 1}]
    assert record(s, allocations=partial).status_code == 400
    payment = ok(record(s))
    assert post(s["client"], f"/api/v1/payments/{payment['id']}/verify", {"allocations": wrong}).status_code == 400
    matching = [{"booking_participant_id": a["booking_participant_id"], "amount_idr": a["amount_idr"]} for a in payment["allocations"]]
    assert ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify", {"allocations": matching}))["status"] == "VERIFIED"


def test_financial_snapshots_immutable(scenario):
    s = scenario()
    invoice = TravelInvoice.objects.without_tenant_guard().get(pk=s["invoice"]["id"])
    invoice.total_idr += 1
    with pytest.raises(ValidationError):
        invoice.save()
    with pytest.raises(ValidationError):
        invoice.delete()
    payment = ok(record(s))
    ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify"))
    receipt = TravelReceipt.objects.without_tenant_guard().get(payment_id=payment["id"])
    with pytest.raises(ValidationError):
        receipt.delete()
    with pytest.raises(ValidationError):
        receipt.save()


def test_cancel_before_verified_payment_voids_invoice(scenario):
    s = scenario()
    payment = ok(record(s))
    ok(post(s["client"], f"/api/v1/bookings/{s['booking']['id']}/transition", {"target": "CANCELED", "reason": "Batal"}))
    invoice = ok(s["client"].get(f"/api/v1/invoices/{s['invoice']['id']}"))
    assert invoice["status"] == "VOIDED"
    assert post(s["client"], f"/api/v1/payments/{payment['id']}/verify").status_code == 400


def test_room_validation_and_existing_single_price(scenario):
    s = scenario(rooms=False)
    assert s["invoice"]["total_idr"] == 84_000_000
    assert PackageRoomPrice.objects.without_tenant_guard().count() == 0
    duplicate = [{"room_type": "QUAD", "price_idr": 1}, {"room_type": "QUAD", "price_idr": 2}]
    assert patch(s["client"], f"/api/v1/packages/{s['package']['id']}", {"room_prices": duplicate}).status_code == 400
    for price in [-1, 10_000_000_001, "1.5"]:
        assert patch(s["client"], f"/api/v1/packages/{s['package']['id']}", {"room_prices": [{"room_type": "QUAD", "price_idr": price}]}).status_code == 400


def test_optional_dp_target_settings(scenario):
    s = scenario(maker_checker=True)
    url = "/api/v1/payments/settings"
    saved = ok(patch(s["client"], url, {"dp_minimum_idr": 5_000_000}))
    assert saved["dp_policy"] == "any_positive" and saved["maker_checker"] is True
    assert ok(patch(s["client"], url, {"dp_minimum_idr": 0}))["dp_minimum_idr"] == 0
    assert patch(s["client"], url, {"dp_minimum_idr": -1}).status_code == 400
    assert patch(s["client"], url, {"dp_policy": "minimum"}).status_code == 400


def test_pdf_failure_rolls_back_verification(scenario, monkeypatch):
    s = scenario()
    payment = ok(record(s))
    def fail(*args, **kwargs):
        raise RuntimeError("PDF failure")
    monkeypatch.setattr("modules.payments.services.render_financial_pdf", fail)
    with pytest.raises(RuntimeError, match="PDF failure"):
        post(s["client"], f"/api/v1/payments/{payment['id']}/verify")
    saved = TravelPayment.objects.without_tenant_guard().get(pk=payment["id"])
    assert saved.status == "SUBMITTED" and saved.verified_at is None
    assert TravelReceipt.objects.without_tenant_guard().count() == 0
    assert PaymentEvent.objects.without_tenant_guard().count() == 0


def test_recording_idempotency_and_unique_reference(scenario):
    s = scenario()
    body = {"invoice": s["invoice"]["id"], "amount_idr": 10, "kind": "DP", "method": "CASH", "received_at": timezone.now().isoformat(), "reference": "TRANSFER-ONCE", "simulate": True, "allocations": [{"booking_participant_id": s["invoice"]["lines"][0]["participant_id"], "amount_idr": 10}]}
    first = ok(post(s["client"], "/api/v1/payments", body, key="record-once"))
    assert ok(post(s["client"], "/api/v1/payments", body, key="record-once")) == first
    assert post(s["client"], "/api/v1/payments", {**body, "reference": "DIFFERENT"}, key="record-once").status_code == 409
    assert post(s["client"], "/api/v1/payments", body).status_code == 409
    assert TravelPayment.objects.without_tenant_guard().count() == 1


def test_invalid_query_and_unknown_financial_fields_return_400(scenario):
    s = scenario()
    for url in ["/api/v1/invoices?booking=invalid", "/api/v1/payments?invoice=invalid", "/api/v1/payments?status=invalid", "/api/v1/invoices?status=invalid"]:
        assert s["client"].get(url).status_code == 400
    assert post(s["client"], f"/api/v1/bookings/{s['booking']['id']}/issue-invoice", {"total_idr": 1}).status_code == 400
    assert patch(s["client"], "/api/v1/payments/settings", {"unknown": "data"}).status_code == 400


def test_fully_allocated_payment_pays_invoice_without_changing_pdf(scenario):
    s = scenario()
    original = s["client"].get(f"/api/v1/invoices/{s['invoice']['id']}/pdf").content
    allocations = [{"booking_participant_id": line["participant_id"], "amount_idr": line["amount_idr"]} for line in s["invoice"]["lines"]]
    payment = ok(record(s, amount=s["invoice"]["total_idr"], allocations=allocations))
    verified = ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify"))
    assert all(p["status"] == "CONFIRMED" for p in verified["participants"])
    invoice = ok(s["client"].get(f"/api/v1/invoices/{s['invoice']['id']}"))
    assert invoice["status"] == "PAID" and invoice["balance_idr"] == 0
    assert s["client"].get(f"/api/v1/invoices/{s['invoice']['id']}/pdf").content == original
    assert ok(post(s["client"], f"/api/v1/bookings/{s['booking']['id']}/transition", {"target": "CONFIRMED"}))["status"] == "CONFIRMED"


@pytest.mark.django_db
def test_payment_role_migration_preserves_custom_roles(tenant_a, tenant_b):
    from importlib import import_module
    from types import SimpleNamespace

    from django.apps import apps
    from django.db import connection

    migration = import_module("modules.tenants.migrations.0006_payment_role_defaults")
    for name, grants in migration.BASELINE.items():
        Role.objects.create(tenant=tenant_a, name=name, permissions_json=grants)
    custom = Role.objects.create(tenant=tenant_b, name="Finance", permissions_json=["invoices.read"])
    for _ in range(2):
        migration.upgrade_payment_roles(apps, SimpleNamespace(connection=connection))
        # Defaults now include S12 wallet grants; exercise the full upgrade path.
        import_module("modules.tenants.migrations.0007_wallet_role_defaults").upgrade(apps, SimpleNamespace(connection=connection))
        import_module("modules.tenants.migrations.0008_notification_role_defaults").upgrade(apps, SimpleNamespace(connection=connection))
        import_module("modules.tenants.migrations.0009_report_role_defaults").upgrade(apps, SimpleNamespace(connection=connection))
        import_module("modules.tenants.migrations.0011_lead_role_defaults").upgrade(apps, SimpleNamespace(connection=connection))
        import_module("modules.tenants.migrations.0012_agent_commission_role_defaults").upgrade(apps, SimpleNamespace(connection=connection))  # agen & komisi
        import_module("modules.tenants.migrations.0014_branch_role_defaults").upgrade(apps, SimpleNamespace(connection=connection))  # cabang
    for role in Role.objects.filter(tenant=tenant_a):
        assert set(role.permissions_json) == set(DEFAULT_ROLE_PERMISSIONS[role.name])
    assert "payments.verify" not in DEFAULT_ROLE_PERMISSIONS["Admin"]
    custom.refresh_from_db()
    assert custom.permissions_json == ["invoices.read"]


def test_financial_rls_denies_without_context_and_other_tenants(scenario, tenant_b):
    from django.db import connection

    s = scenario()
    role = "pay_rls_" + uuid4().hex[:12]
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE ROLE "{role}" NOLOGIN')
        cursor.execute(f'GRANT USAGE ON SCHEMA public TO "{role}"')
        cursor.execute(f'GRANT SELECT ON payments_travelinvoice TO "{role}"')
        try:
            cursor.execute(f'SET LOCAL ROLE "{role}"')
            for tenant_id, expected in [("", 0), (str(s["tenant"].pk), 1), (str(tenant_b.pk), 0)]:
                cursor.execute("SELECT set_config('app.tenant_id',%s,TRUE)", [tenant_id])
                cursor.execute("SELECT count(*) FROM payments_travelinvoice")
                assert cursor.fetchone()[0] == expected
        finally:
            cursor.execute("RESET ROLE")


def test_invoice_due_config_and_unimplemented_tax_are_not_ignored(scenario):
    from datetime import timedelta

    from modules.audit.models import AuditEvent
    from modules.payments.dates import tenant_today
    from modules.tenants.models import TenantSettings

    s = scenario(issue=False)
    settings = TenantSettings.objects.get(tenant=s["tenant"])
    settings.invoice_config_json = {"due_days": 10, "tax_idr": 1000}
    settings.save(update_fields=["invoice_config_json"])
    pilgrim = ok(post(s["client"], "/api/v1/pilgrims", {"name": "Jamaah Pajak"}))
    booking = ok(post(s["client"], "/api/v1/bookings", {"departure": s["departure"]["id"], "participants": [pilgrim["id"]], "room_types": {pilgrim["id"]: "QUAD"}}))
    # INV-01 otomatis gagal karena pajak belum didukung → reservasi tetap sah, kegagalan diaudit.
    assert ok(post(s["client"], f"/api/v1/bookings/{booking['id']}/transition", {"target": "RESERVED"}))["status"] == "RESERVED"
    assert AuditEvent.objects.filter(action="invoice.auto_issue_failed", object_id=str(booking["id"])).exists()
    url = f"/api/v1/bookings/{booking['id']}/issue-invoice"
    assert post(s["client"], url).status_code == 400
    settings.invoice_config_json = {"due_days": 10}
    settings.rules_json = {}  # target DP boleh tidak diisi sama sekali
    settings.save(update_fields=["invoice_config_json", "rules_json"])
    invoice = ok(post(s["client"], url))
    assert invoice["due_at"] == (tenant_today(s["tenant"]) + timedelta(days=10)).isoformat()
    assert invoice["dp_policy"] == {"dp_policy": "any_positive", "dp_minimum_idr": 0}


def test_legacy_active_participant_keeps_status_when_dp_becomes_eligible(scenario):
    from modules.booking.models import BookingParticipant

    s = scenario(environment="production")
    pid = s["invoice"]["lines"][0]["participant_id"]
    BookingParticipant.objects.without_tenant_guard().filter(pk=pid).update(participant_status="DEPARTED")
    payment = ok(record(s, amount=1))
    verified = ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify"))
    participant = next(row for row in verified["participants"] if row["id"] == pid)
    assert participant["status"] == "DEPARTED"
    assert participant["dp_eligible_at"] and participant["saas_charge_state"] == "pending_charge"
