"""S13: DP verified → exactly-once SaaS charge, pending FIFO retry, refunds and ledger consistency."""
from io import StringIO
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError as ModelValidationError
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.utils import timezone

from modules.billing.models import BillingEvent, SaaSAdjustment, SaaSCharge, SaaSPriceVersion
from modules.booking.models import BookingParticipant
from modules.identity.models import User
from modules.payments.models import TravelReceipt
from modules.tenants.models import Role, Tenant, TenantMembership
from modules.wallet.models import Wallet, WalletLedger
from modules.wallet.services import platform_tenant_context, reconcile_wallet

from .conftest import mark_platform_mfa
from .test_payment_security import staff
from .test_payments import ok, post
from .test_payments import scenario as scenario
from .test_wallet import settle, topup
from .test_wallet import wallet_setup as wallet_setup


@pytest.fixture
def billing(wallet_setup, scenario):
    s = wallet_setup
    refunds = User.objects.create_user(email="refunds@example.test", password="test-123456", status="ACTIVE", is_staff=True, email_verified_at=timezone.now())
    refunds.user_permissions.add(Permission.objects.get(content_type__app_label="billing", codename="approve_adjustment"))
    s["refunds"] = Client()
    s["refunds"].force_login(refunds)
    mark_platform_mfa(s["refunds"])
    s["travel"] = scenario(environment="production")
    return s


def fund(s, amount):
    return ok(settle(s, topup(s, amount)))


def pay(s, indices=(0,), amount=1_000_000, kind="DP", verify=True, client=None):
    travel = s["travel"]
    body = {
        "invoice": travel["invoice"]["id"], "amount_idr": amount * len(indices), "kind": kind, "method": "CASH",
        "received_at": timezone.now().isoformat(), "reference": f"REF-{uuid4().hex[:12]}",
        "allocations": [{"booking_participant_id": travel["invoice"]["lines"][i]["participant_id"], "amount_idr": amount} for i in indices],
    }
    payment = ok(post(travel["client"], "/api/v1/payments", body))
    return ok(post(client or travel["client"], f"/api/v1/payments/{payment['id']}/verify")) if verify else payment


def participant(s, index=0):
    return BookingParticipant.objects.without_tenant_guard().get(pk=s["travel"]["invoice"]["lines"][index]["participant_id"])


def charges(**filters):
    return SaaSCharge.objects.without_tenant_guard().filter(**filters)


def summary(s):
    return ok(s["client"].get("/api/v1/wallet"))


def tenant_state(s):
    return Tenant.objects.get(pk=s["tenant"].pk).state


def reconciled(s):
    with platform_tenant_context(s["tenant"].pk):
        return reconcile_wallet()


def cancel_booking(s, reason="Jamaah membatalkan"):
    return ok(post(s["travel"]["client"], f"/api/v1/bookings/{s['travel']['booking']['id']}/transition", {"target": "CANCELED", "reason": reason}))


def test_pay01_verified_dp_charges_once_and_confirms(billing):
    s = billing
    fund(s, 100_000)
    verified = pay(s)
    row = next(p for p in verified["participants"] if p["dp_eligible_at"])
    assert row["saas_charge_status"] == "POSTED" and row["unit_fee_idr"] == 50_000
    assert row["status"] == "CONFIRMED" and row["saas_charge_state"] == "charged"
    assert summary(s)["balance_idr"] == 50_000
    charge = charges().get()
    debit = WalletLedger.objects.without_tenant_guard().get(kind="DEBIT")
    assert charge.status == "POSTED" and charge.ledger_entry_id == debit.pk
    assert debit.reference_id == charge.pk and debit.signed_amount_idr == -50_000
    assert charge.price_version.code == "STD-2026" and charge.unit_price_idr == 50_000
    assert BillingEvent.objects.without_tenant_guard().filter(kind="saas.charge.posted").count() == 1
    result = reconciled(s)
    assert result.consistent and result.details_json["charges_ok"] and result.details_json["orphan_debits"] == 0


def test_pay03_zero_wallet_keeps_dp_receipt_and_restricts(billing):
    s = billing
    verified = pay(s)
    assert verified["status"] == "VERIFIED" and verified["receipt"]["status"] == "ISSUED"
    row = next(p for p in verified["participants"] if p["dp_eligible_at"])
    assert row["saas_charge_status"] == "PENDING_INSUFFICIENT_FUNDS" and row["status"] == "DP_VERIFIED_PENDING_CHARGE"
    assert Wallet.objects.without_tenant_guard().count() == 0  # verification never provisions a wallet
    assert tenant_state(s) == "RESTRICTED"
    data = summary(s)
    assert data["pending_charge_count"] == 1 and data["pending_charge_idr"] == 50_000 and data["tenant_state"] == "RESTRICTED"
    assert BillingEvent.objects.without_tenant_guard().filter(kind="saas.charge.pending").count() == 1
    blocked = post(s["travel"]["client"], f"/api/v1/bookings/{s['travel']['booking']['id']}/transition", {"target": "CONFIRMED"})
    assert blocked.status_code == 400
    # RESTRICTED still allows wallet top-up and day-to-day work.
    assert summary(s)["topup_available"]


def test_pay04_topup_settles_pending_once_and_lifts_restriction(billing):
    s = billing
    pay(s)
    t = topup(s, 100_000)
    first = ok(settle(s, t))
    assert ok(settle(s, t)) == first  # bank replay
    charge = charges().get()
    assert charge.status == "POSTED" and charge.attempts == 1
    assert participant(s).participant_status == "CONFIRMED"
    assert summary(s)["balance_idr"] == 50_000 and tenant_state(s) == "ACTIVE"
    assert ok(post(s["client"], "/api/v1/wallet/charges/retry")) == {"posted": 0, "pending": 0, "voided": 0}
    assert WalletLedger.objects.without_tenant_guard().filter(kind="DEBIT").count() == 1
    assert reconciled(s).consistent


def test_pay06_group_dp_allocated_to_one_participant_charges_one(billing):
    s = billing
    fund(s, 500_000)
    verified = pay(s, indices=(0,), amount=3_000_000)
    assert sum(p["saas_charge_status"] == "POSTED" for p in verified["participants"]) == 1
    assert charges().count() == 1 and summary(s)["balance_idr"] == 450_000


def test_multi_participant_allocation_charges_each(billing):
    s = billing
    fund(s, 500_000)
    verified = pay(s, indices=(0, 1, 2))
    assert [p["saas_charge_status"] for p in verified["participants"]] == ["POSTED"] * 3
    assert summary(s)["balance_idr"] == 350_000


def test_pay07_second_installment_never_charges_again(billing):
    s = billing
    fund(s, 500_000)
    pay(s)
    pay(s, kind="INSTALLMENT", amount=2_000_000)
    pay(s, kind="INSTALLMENT", amount=3_000_000)
    assert charges().count() == 1 and WalletLedger.objects.without_tenant_guard().filter(kind="DEBIT").count() == 1
    assert summary(s)["balance_idr"] == 450_000


def test_pay08_cancel_before_verified_dp_never_charges(billing):
    s = billing
    fund(s, 100_000)
    pay(s, verify=False)
    cancel_booking(s)
    assert charges().count() == 0 and summary(s)["balance_idr"] == 100_000


def test_cancel_with_pending_charge_voids_and_unrestricts(billing):
    s = billing
    pay(s)
    assert tenant_state(s) == "RESTRICTED"
    cancel_booking(s)
    charge = charges().get()
    assert charge.status == "VOID" and "membatalkan" in charge.void_reason
    assert tenant_state(s) == "ACTIVE"
    fund(s, 100_000)
    assert summary(s)["balance_idr"] == 100_000  # voided charge never retried


def test_pay09_cancel_after_posted_charge_requires_approved_refund(billing):
    s = billing
    fund(s, 100_000)
    pay(s)
    cancel_booking(s)
    assert summary(s)["balance_idr"] == 50_000  # no automatic refund
    listed = ok(s["client"].get("/api/v1/wallet/charges"))["results"][0]
    assert listed["status"] == "POSTED" and listed["refundable"] and listed["pilgrim_name"]
    url = f"/api/v1/wallet/charges/{listed['id']}/refund-request"
    assert post(s["client"], url, {"reason": "x"}).status_code == 400
    requested = ok(post(s["client"], url, {"reason": "Jamaah batal sebelum proses visa"}))
    assert requested["status"] == "REQUESTED" and requested["amount_idr"] == 50_000
    assert ok(post(s["client"], url, {"reason": "Jamaah batal sebelum proses visa"}))["id"] == requested["id"]
    assert post(s["client"], url, {"reason": "Alasan lain berbeda"}).status_code == 409
    assert summary(s)["balance_idr"] == 50_000  # request alone never credits
    platform_list = ok(s["refunds"].get(f"/api/v1/platform/tenants/{s['tenant'].pk}/wallet/refunds?status=REQUESTED"))
    assert platform_list["count"] == 1 and "pilgrim_name" not in platform_list["results"][0]
    decide = f"/api/v1/platform/tenants/{s['tenant'].pk}/wallet/refunds/{requested['id']}/decide"
    body = {"decision": "APPROVED", "reason": "Kebijakan pembatalan disetujui"}
    approved = ok(post(s["refunds"], decide, body))
    assert approved["status"] == "APPROVED" and approved["ledger_entry_id"]
    for _ in range(3):  # SEC03 replay
        assert ok(post(s["refunds"], decide, body)) == approved
    assert post(s["refunds"], decide, {"decision": "REJECTED", "reason": "x"}).status_code == 409
    assert WalletLedger.objects.without_tenant_guard().filter(kind="REFUND").count() == 1
    assert summary(s)["balance_idr"] == 100_000
    charge = charges().get()
    assert charge.status == "REFUNDED" and participant(s).saas_charge_state == "reversed"
    assert ok(post(s["client"], url, {"reason": "Jamaah batal sebelum proses visa"}))["status"] == "APPROVED"  # replay
    assert post(s["client"], url, {"reason": "Permintaan kedua"}).status_code == 409
    assert SaaSAdjustment.objects.without_tenant_guard().count() == 1
    result = reconciled(s)
    assert result.consistent and result.details_json["refunds_ok"]


def test_refund_rules_permissions_and_rejection(billing):
    s = billing
    fund(s, 100_000)
    pay(s)
    charge = charges().get()
    url = f"/api/v1/wallet/charges/{charge.pk}/refund-request"
    assert post(s["client"], url, {"reason": "Belum dibatalkan"}).status_code == 400  # participant still active
    cancel_booking(s)
    finance = staff(s["tenant"], "Finance")
    assert post(finance, url, {"reason": "Finance tidak berwenang"}).status_code == 403
    requested = ok(post(s["client"], url, {"reason": "Pembatalan sesuai kontrak"}))
    decide = f"/api/v1/platform/tenants/{s['tenant'].pk}/wallet/refunds/{requested['id']}/decide"
    # Tenant Owner wildcard and platform settlement permission are not refund authority.
    assert post(s["client"], decide, {"decision": "APPROVED", "reason": "ok"}).status_code == 403
    assert post(s["platform"], decide, {"decision": "APPROVED", "reason": "ok"}).status_code == 403
    assert post(s["refunds"], decide, {"decision": "APPROVED", "reason": " "}).status_code == 400
    assert post(s["refunds"], decide, {"decision": "MAYBE", "reason": "ok"}).status_code == 400
    # The requester cannot approve their own request even with platform rights.
    s["owner"].is_staff = True
    s["owner"].save(update_fields=["is_staff"])
    s["owner"].user_permissions.add(Permission.objects.get(content_type__app_label="billing", codename="approve_adjustment"))
    mark_platform_mfa(s["client"])
    assert post(s["client"], decide, {"decision": "APPROVED", "reason": "ok"}).status_code == 403
    rejected = ok(post(s["refunds"], decide, {"decision": "REJECTED", "reason": "Di luar kebijakan"}))
    assert rejected["status"] == "REJECTED" and rejected["ledger_entry_id"] is None
    assert summary(s)["balance_idr"] == 50_000
    # A rejected request may be followed by a new, separately reviewed one.
    assert ok(post(s["client"], url, {"reason": "Bukti pembatalan baru"}))["status"] == "REQUESTED"


def test_reversal_voids_pending_and_new_epoch_charges_again(billing):
    s = billing
    first = pay(s)
    finance = staff(s["tenant"], "Finance")
    ok(post(finance, f"/api/v1/payments/{first['id']}/reverse", {"reason": "Transfer gagal kliring"}))
    assert charges(status="VOID").count() == 1 and tenant_state(s) == "ACTIVE"
    p = participant(s)
    assert p.saas_charge_state == "not_eligible" and p.participant_status == "REVIEW_REQUIRED"
    fund(s, 100_000)
    pay(s)
    assert charges(status="POSTED").count() == 1 and charges().count() == 2
    assert BillingEvent.objects.without_tenant_guard().filter(kind="saas.charge.pending").count() == 1


def test_reversal_after_posted_charge_keeps_charge(billing):
    s = billing
    fund(s, 100_000)
    verified = pay(s)
    finance = staff(s["tenant"], "Finance")
    ok(post(finance, f"/api/v1/payments/{verified['id']}/reverse", {"reason": "Salah input"}))
    assert charges().get().status == "POSTED" and summary(s)["balance_idr"] == 50_000
    assert participant(s).participant_status == "REVIEW_REQUIRED"
    pay(s)  # re-verified DP: participant already charged
    assert charges().count() == 1 and summary(s)["balance_idr"] == 50_000
    assert reconciled(s).consistent


def test_pending_queue_is_fifo_and_stops_when_funds_run_out(billing):
    s = billing
    pay(s, indices=(1,))
    pay(s, indices=(0,))
    pay(s, indices=(2,))
    order = list(charges().order_by("eligible_at").values_list("participant_id", flat=True))
    fund(s, 60_000)
    posted = charges(status="POSTED").get()
    assert posted.participant_id == order[0]
    assert charges(status="PENDING").count() == 2 and tenant_state(s) == "RESTRICTED"
    assert summary(s)["balance_idr"] == 10_000
    fund(s, 100_000)
    assert charges(status="POSTED").count() == 3 and tenant_state(s) == "ACTIVE"
    assert summary(s)["balance_idr"] == 10_000


def test_frozen_wallet_pending_then_commands_retry(billing):
    s = billing
    fund(s, 100_000)
    Wallet.objects.without_tenant_guard().update(status="FROZEN")
    verified = pay(s)
    assert next(p for p in verified["participants"] if p["dp_eligible_at"])["saas_charge_status"] == "PENDING_WALLET_UNAVAILABLE"
    Wallet.objects.without_tenant_guard().update(status="ACTIVE")
    out = StringIO()
    call_command("retry_pending_charges", stdout=out)
    assert "posted=1" in out.getvalue()
    call_command("retry_pending_charges", stdout=out)
    assert charges(status="POSTED").count() == 1 and summary(s)["balance_idr"] == 50_000
    call_command("reconcile_wallets", stdout=StringIO())


def test_reconcile_command_retries_pending_after_consistent_check(billing):
    s = billing
    fund(s, 100_000)
    Wallet.objects.without_tenant_guard().update(status="FROZEN")
    pay(s)
    Wallet.objects.without_tenant_guard().update(status="ACTIVE")
    call_command("reconcile_wallets", stdout=StringIO())
    assert charges(status="POSTED").count() == 1


def test_charge_preview_shows_fee_balance_and_hides_wallet_without_grant(billing):
    s = billing
    fund(s, 60_000)
    pay(s, indices=(1,))  # posted, leaves 10.000
    payment = pay(s, indices=(0, 1), verify=False)
    preview = ok(s["client"].get(f"/api/v1/payments/{payment['id']}/charge-preview"))
    rows = {row["booking_participant_id"]: row for row in preview["participants"]}
    assert rows[s["travel"]["invoice"]["lines"][1]["participant_id"]]["already_charged"]
    assert preview["total_fee_idr"] == 50_000 and preview["wallet_balance_idr"] == 10_000
    assert not preview["sufficient"] and preview["balance_after_idr"] == -40_000
    verifier = User.objects.create_user(email="verifier@example.test", status="ACTIVE", email_verified_at=timezone.now())
    role = Role.objects.create(tenant=s["tenant"], name="Verifier", permissions_json=["payments.verify", "payments.read", "payments.read_all"])
    TenantMembership.objects.without_tenant_guard().create(tenant=s["tenant"], user=verifier, role=role, status="ACTIVE")
    client = Client()
    client.force_login(verifier)
    limited = ok(client.get(f"/api/v1/payments/{payment['id']}/charge-preview"))
    assert "wallet_balance_idr" not in limited and limited["total_fee_idr"] == 50_000


def test_demo_verification_never_creates_charges(scenario):
    s = scenario(environment="demo")
    from .test_payments import record

    payment = ok(record(s))
    verified = ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify"))
    assert all(p["saas_charge_status"] is None for p in verified["participants"])
    assert SaaSCharge.objects.without_tenant_guard().count() == 0
    preview = ok(s["client"].get(f"/api/v1/payments/{payment['id']}/charge-preview"))
    assert not preview["charges_applicable"]


def test_charge_list_filters_and_ledger_refund_kind(billing):
    s = billing
    pay(s)
    assert ok(s["client"].get("/api/v1/wallet/charges?status=PENDING"))["count"] == 1
    assert ok(s["client"].get("/api/v1/wallet/charges?status=POSTED"))["count"] == 0
    assert s["client"].get("/api/v1/wallet/charges?status=FORGED").status_code == 400
    assert s["client"].get("/api/v1/wallet/ledger?kind=REFUND").status_code == 200
    sales = staff(s["tenant"], "Sales")
    assert sales.get("/api/v1/wallet/charges").status_code == 403
    assert post(sales, "/api/v1/wallet/charges/retry").status_code == 403


def test_database_guards_on_charges_events_and_prices(billing):
    s = billing
    fund(s, 100_000)
    pay(s)
    charge = charges().get()
    with pytest.raises(ModelValidationError):
        charge.unit_price_idr = 1
        charge.save()
    with pytest.raises(ModelValidationError):
        charge.delete()
    for sql in [
        "UPDATE billing_saascharge SET unit_price_idr = 1",
        "UPDATE billing_saascharge SET status = 'PENDING'",
        "UPDATE billing_saascharge SET status = 'REFUNDED'",  # no approved credit
        "DELETE FROM billing_saascharge",
        "UPDATE billing_billingevent SET kind = 'forged'",
        "DELETE FROM billing_billingevent",
        "UPDATE billing_saaspriceversion SET unit_price_idr = 1",
    ]:
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(sql)
    with pytest.raises(ModelValidationError):
        SaaSPriceVersion.objects.get(code="STD-2026").save()
    assert charges().get().unit_price_idr == 50_000


def test_charge_must_belong_to_verified_production_participant(billing):
    s = billing
    p = participant(s)
    price = SaaSPriceVersion.objects.get(code="STD-2026")
    payment = pay(s, verify=False)
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, TRUE)", [str(s["tenant"].pk)])
        cursor.execute(
            "INSERT INTO billing_saascharge (id, created_at, updated_at, tenant_id, participant_id, booking_id, source_payment_id, charge_type, unit_price_idr, price_version_id, status, pending_reason, eligible_at, attempts, void_reason)"
            " VALUES (%s, now(), now(), %s, %s, %s, %s, 'initial', 50000, %s, 'PENDING', '', now(), 0, '')",
            [str(uuid4()), str(s["tenant"].pk), str(p.pk), str(p.booking_id), payment["id"], str(price.pk)],
        )


def test_unique_open_charge_per_participant(billing):
    s = billing
    pay(s)
    charge = charges().get()
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, TRUE)", [str(s["tenant"].pk)])
        cursor.execute(
            "INSERT INTO billing_saascharge (id, created_at, updated_at, tenant_id, participant_id, booking_id, source_payment_id, charge_type, unit_price_idr, price_version_id, status, pending_reason, eligible_at, attempts, void_reason)"
            " SELECT %s, now(), now(), tenant_id, participant_id, booking_id, source_payment_id, 'initial', 50000, price_version_id, 'PENDING', '', now(), 0, '' FROM billing_saascharge WHERE id = %s",
            [str(uuid4()), str(charge.pk)],
        )


@pytest.mark.parametrize("table", ["billing_saascharge", "billing_saasadjustment", "billing_billingevent"])
def test_billing_tables_enforce_rls(db, table):
    with connection.cursor() as cursor:
        cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=%s", [table])
        assert cursor.fetchone() == (True, True)


def test_real_rls_on_charges_without_superuser(billing, tenant_b):
    s = billing
    pay(s)
    role = "billing_rls_" + uuid4().hex[:12]
    tables = ["billing_saascharge", "billing_billingevent"]
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE ROLE "{role}" NOLOGIN')
        cursor.execute(f'GRANT USAGE ON SCHEMA public TO "{role}"')
        cursor.execute(f'GRANT SELECT ON {", ".join(tables)} TO "{role}"')
        try:
            cursor.execute(f'SET LOCAL ROLE "{role}"')
            for tenant_id, expected in [("", 0), (str(s["tenant"].pk), 1), (str(tenant_b.pk), 0)]:
                cursor.execute("SELECT set_config('app.tenant_id', %s, TRUE)", [tenant_id])
                for table in tables:
                    cursor.execute(f"SELECT count(*) FROM {table}")
                    assert cursor.fetchone()[0] == expected, (table, tenant_id)
        finally:
            cursor.execute("RESET ROLE")
            cursor.execute(f'REVOKE ALL ON {", ".join(tables)} FROM "{role}"')
            cursor.execute(f'REVOKE USAGE ON SCHEMA public FROM "{role}"')
            cursor.execute(f'DROP ROLE "{role}"')


def test_receipt_issued_even_when_charge_pending(billing):
    s = billing
    pay(s)
    assert TravelReceipt.objects.without_tenant_guard().count() == 1
    assert SaaSAdjustment.objects.without_tenant_guard().count() == 0


def test_missing_price_row_never_blocks_verification(billing):
    s = billing
    with connection.cursor() as cursor:
        # Simulates an operator wiping the platform table; bypasses the append-only trigger.
        cursor.execute("SET LOCAL session_replication_role = replica")
        cursor.execute("DELETE FROM billing_saaspriceversion")
        cursor.execute("SET LOCAL session_replication_role = origin")
    fund(s, 100_000)
    verified = pay(s)
    assert next(p for p in verified["participants"] if p["dp_eligible_at"])["saas_charge_status"] == "POSTED"
    assert SaaSPriceVersion.objects.get().unit_price_idr == 50_000
