"""S12: real PostgreSQL transactions, security and prepaid financial invariants."""
from datetime import timedelta
from importlib import import_module
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError as ModelValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction
from django.test import Client
from django.utils import timezone

from modules.identity.models import User
from modules.tenants.models import Role, TenantEnvironment
from modules.tenants.rbac import DEFAULT_ROLE_PERMISSIONS
from modules.wallet.models import Wallet, WalletEvent, WalletLedger, WalletOperation, WalletReconciliation, WalletTopup
from modules.wallet.services import Conflict, atomic_debit, platform_tenant_context, reconcile_wallet

from .test_payments import ok, post, record
from .test_payments import scenario as scenario


@pytest.fixture
def wallet_setup(auth_client, tenant_a, user, settings):
    tenant_a.state = "ACTIVE"
    tenant_a.save(update_fields=["state"])
    TenantEnvironment.objects.create(tenant=tenant_a, environment="production", state="ACTIVE")
    settings.WALLET_MANUAL_BANK_NAME = "BANK UJI"
    settings.WALLET_MANUAL_ACCOUNT_NAME = "PT Platform Uji"
    settings.WALLET_MANUAL_ACCOUNT_NUMBER = "000123456"
    billing = User.objects.create_user(email="billing@example.test", password="test-123456", status="ACTIVE", is_staff=True, email_verified_at=timezone.now())
    billing.user_permissions.add(Permission.objects.get(content_type__app_label="wallet", codename="settle_topup"))
    platform = Client()
    platform.force_login(billing)
    return {"client": auth_client, "tenant": tenant_a, "owner": user, "billing": billing, "platform": platform}


def topup(s, amount=100_000, *, submit=True, key=None):
    result = ok(post(s["client"], "/api/v1/wallet/topups", {"amount_idr": amount}, key=key))
    if submit:
        result = ok(post(s["client"], f"/api/v1/wallet/topups/{result['id']}/submit", {"payment_reference": f"TRANSFER-{result['id']}", "evidence_ref": "restricted://test-evidence"}))
    return result


def settle(s, t, **changes):
    body = {"amount_idr": t["amount_idr"], "provider_txn_id": f"BANK-{t['id']}", **changes}
    return post(s["platform"], f"/api/v1/platform/tenants/{s['tenant'].pk}/wallet/topups/{t['id']}/settle", body)


def balance(s):
    return ok(s["client"].get("/api/v1/wallet"))


def test_create_submit_never_credit_and_settlement_once(wallet_setup):
    s = wallet_setup
    assert balance(s)["balance_idr"] == 0
    assert Wallet.objects.without_tenant_guard().count() == 0  # GET is read-only
    t = topup(s)
    assert t["status"] == "PENDING" and balance(s)["balance_idr"] == 0
    first = ok(settle(s, t))
    assert first["status"] == "PAID" and first["ledger_entry_id"]
    for _ in range(3):
        assert ok(settle(s, t)) == first
    summary = balance(s)
    assert summary["balance_idr"] == summary["ledger_balance_idr"] == 100_000
    assert summary["estimated_participant_capacity"] == 2 and summary["version"] == 1
    assert WalletLedger.objects.without_tenant_guard().count() == WalletEvent.objects.without_tenant_guard().count() == 1
    assert settle(s, t, provider_txn_id="OTHER").status_code == 409
    assert settle(s, t, amount_idr=100_001).status_code == 400


def test_idempotency_binds_amount_and_key_required(wallet_setup):
    s = wallet_setup
    a = topup(s, submit=False, key="create-one")
    assert topup(s, submit=False, key="create-one")["id"] == a["id"]
    assert post(s["client"], "/api/v1/wallet/topups", {"amount_idr": 200_000}, key="create-one").status_code == 409
    assert post(s["client"], "/api/v1/wallet/topups", {"amount_idr": 100_000}, key=" " ).status_code == 400
    assert WalletOperation.objects.without_tenant_guard().count() == 1


@pytest.mark.parametrize("amount", [0, -1, 1.5, True, "50000", 10_000_000_001])
def test_invalid_amounts(wallet_setup, amount):
    assert post(wallet_setup["client"], "/api/v1/wallet/topups", {"amount_idr": amount}).status_code == 400
    assert WalletLedger.objects.without_tenant_guard().count() == 0


def test_optional_minimum_and_unknown_field(wallet_setup):
    s = wallet_setup
    assert topup(s, amount=1, submit=False)["amount_idr"] == 1
    for extra in [{"tenant_id": str(s["tenant"].pk)}, {"status": "PAID"}, {"provider": "fake"}, {"balance_idr": 999999}]:
        assert post(s["client"], "/api/v1/wallet/topups", {"amount_idr": 1, **extra}).status_code == 400


def test_missing_platform_bank_configuration_disables_new_requests(wallet_setup, settings):
    s = wallet_setup
    settings.WALLET_MANUAL_ACCOUNT_NUMBER = ""
    assert not balance(s)["topup_available"]
    assert post(s["client"], "/api/v1/wallet/topups", {"amount_idr": 100_000}).status_code == 400
    assert WalletTopup.objects.without_tenant_guard().count() == 0


def test_demo_cannot_fund_or_create_real_wallet(wallet_setup):
    s = wallet_setup
    TenantEnvironment.objects.filter(tenant=s["tenant"]).delete()
    TenantEnvironment.objects.create(tenant=s["tenant"], environment="demo", state="ACTIVE")
    summary = balance(s)
    assert summary["environment"] == "demo" and not summary["topup_available"]
    assert post(s["client"], "/api/v1/wallet/topups", {"amount_idr": 1}).status_code == 403
    assert Wallet.objects.without_tenant_guard().count() == 0


def test_only_authorized_platform_staff_can_settle(wallet_setup):
    s = wallet_setup
    t = topup(s)
    url = f"/api/v1/platform/tenants/{s['tenant'].pk}/wallet/topups/{t['id']}/settle"
    body = {"amount_idr": 100_000, "provider_txn_id": "bank-unique"}
    assert post(s["client"], url, body).status_code == 403  # Owner wildcard is tenant-scoped
    permission = Permission.objects.get(content_type__app_label="wallet", codename="settle_topup")
    s["billing"].user_permissions.remove(permission)
    assert post(s["platform"], url, body).status_code == 403  # is_staff alone insufficient
    s["owner"].is_staff = True
    s["owner"].user_permissions.add(permission)
    s["owner"].save()
    assert post(s["client"], url, body).status_code == 403  # cannot settle own transfer
    assert balance(s)["balance_idr"] == 0


def test_bank_reference_globally_unique_and_mismatch_rolls_back(wallet_setup):
    s = wallet_setup
    first = topup(s)
    second = topup(s)
    ok(settle(s, first, provider_txn_id="SAME-BANK-TRANSFER"))
    assert settle(s, second, provider_txn_id="SAME-BANK-TRANSFER").status_code == 409
    assert balance(s)["balance_idr"] == 100_000
    assert WalletLedger.objects.without_tenant_guard().count() == 1
    assert WalletTopup.objects.without_tenant_guard().get(pk=second["id"]).status == "PENDING"


def test_submit_is_idempotent_and_cannot_replace_evidence(wallet_setup):
    s = wallet_setup
    t = topup(s)
    url = f"/api/v1/wallet/topups/{t['id']}/submit"
    assert ok(post(s["client"], url, {"payment_reference": t["payment_reference"], "evidence_ref": t["evidence_ref"]})) == t
    assert post(s["client"], url, {"payment_reference": "different", "evidence_ref": t["evidence_ref"]}).status_code == 409
    assert post(s["client"], url, {"payment_reference": "", "evidence_ref": ""}).status_code == 400


def test_rejection_requires_reason_and_never_credits(wallet_setup):
    s = wallet_setup
    t = topup(s)
    assert settle(s, t, decision="REJECTED").status_code == 400
    assert ok(settle(s, t, decision="REJECTED", reason="Dana belum diterima"))["status"] == "REJECTED"
    assert balance(s)["balance_idr"] == 0
    assert settle(s, t).status_code == 409


def test_expired_instructions_and_pending_evidence_policy(wallet_setup):
    s = wallet_setup
    yesterday = timezone.now() - timedelta(days=2)
    with patch("modules.wallet.services.timezone.now", return_value=yesterday):
        created = topup(s, submit=False)
        pending = topup(s)
    assert post(s["client"], f"/api/v1/wallet/topups/{created['id']}/submit", {"payment_reference": "late", "evidence_ref": "evidence"}).status_code == 409
    call_command("reconcile_wallets", tenant=s["tenant"].slug, stdout=StringIO())
    assert WalletTopup.objects.without_tenant_guard().get(pk=created["id"]).status == "EXPIRED"
    assert WalletTopup.objects.without_tenant_guard().get(pk=pending["id"]).status == "PENDING"
    assert ok(settle(s, pending))["status"] == "PAID"  # funds can settle later


def test_frozen_and_inactive_tenant_cannot_mutate(wallet_setup):
    s = wallet_setup
    t = topup(s)
    Wallet.objects.without_tenant_guard().update(status="FROZEN")
    assert not balance(s)["topup_available"]
    assert settle(s, t).status_code == 403
    assert post(s["client"], "/api/v1/wallet/topups", {"amount_idr": 1}).status_code == 403
    Wallet.objects.without_tenant_guard().update(status="ACTIVE")
    s["tenant"].state = "SUSPENDED"
    s["tenant"].save()
    assert settle(s, t).status_code == 403
    assert balance(s)["balance_idr"] == 0


def test_restricted_tenant_can_still_top_up(wallet_setup):
    s = wallet_setup
    s["tenant"].state = "RESTRICTED"
    s["tenant"].save(update_fields=["state"])
    assert balance(s)["topup_available"]
    assert ok(settle(s, topup(s)))["status"] == "PAID"


def test_atomic_debit_dedup_and_insufficient_balance(wallet_setup):
    s = wallet_setup
    ok(settle(s, topup(s)))
    reference = uuid4()
    with platform_tenant_context(s["tenant"].pk):
        first = atomic_debit(reference_id=reference, amount_idr=50_000)
        assert atomic_debit(reference_id=reference, amount_idr=50_000).pk == first.pk
        with pytest.raises(Conflict):
            atomic_debit(reference_id=reference, amount_idr=25_000)
        assert atomic_debit(reference_id=uuid4(), amount_idr=50_001) is None
        assert atomic_debit(reference_id=uuid4(), amount_idr=50_000)
        assert atomic_debit(reference_id=uuid4(), amount_idr=1) is None
        result = reconcile_wallet()
        # S13: balance/chain stay exact, but a debit without a SaaSCharge is flagged.
        assert result.ledger_balance_idr == 0 and result.ledger_count == 3 and result.variance_idr == 0
        assert result.details_json["chain_ok"] and result.details_json["orphan_debits"] == 2
        assert not result.consistent
    assert balance(s)["balance_idr"] == 0


def test_entire_settlement_rolls_back_if_outbox_fails(wallet_setup):
    s = wallet_setup
    t = topup(s)
    with patch("modules.wallet.services.WalletEvent.objects.create", side_effect=RuntimeError("outbox unavailable")), pytest.raises(RuntimeError):
        settle(s, t)
    assert balance(s)["balance_idr"] == 0
    assert WalletLedger.objects.without_tenant_guard().count() == 0
    assert WalletTopup.objects.without_tenant_guard().get(pk=t["id"]).status == "PENDING"


def test_ledger_immutable_even_queryset_and_sql(wallet_setup):
    s = wallet_setup
    t = topup(s)
    ok(settle(s, t))
    with platform_tenant_context(s["tenant"].pk):
        row = WalletLedger.objects.get()
        with pytest.raises(ModelValidationError):
            row.save()
        with pytest.raises(ModelValidationError):
            row.delete()
        for action in [lambda: WalletLedger.objects.update(signed_amount_idr=1), lambda: WalletLedger.objects.all().delete(), lambda: WalletEvent.objects.update(kind="forged")]:
            with pytest.raises(DatabaseError), transaction.atomic():
                action()
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE wallet_walletledger SET balance_after_idr = 0 WHERE id = %s", [row.pk])
        with pytest.raises(DatabaseError), transaction.atomic():
            WalletTopup.objects.filter(pk=t["id"]).update(amount_idr=1)
        assert WalletLedger.objects.get().signed_amount_idr == 100_000


def test_reconciliation_detects_without_rewriting_cache(wallet_setup):
    s = wallet_setup
    ok(settle(s, topup(s)))
    Wallet.objects.without_tenant_guard().update(balance_cached_idr=99_999)
    with pytest.raises(CommandError):
        call_command("reconcile_wallets", tenant=s["tenant"].slug, stdout=StringIO())
    result = WalletReconciliation.objects.without_tenant_guard().latest("created_at")
    assert not result.consistent and result.variance_idr == -1
    assert balance(s)["balance_idr"] == 99_999  # no silent auto-correction


def test_cross_tenant_ids_and_roles_are_denied(wallet_setup, tenant_b, owner_a):
    s = wallet_setup
    t = topup(s)
    owner_a.tenant = tenant_b
    owner_a.save(update_fields=["tenant"])
    assert s["client"].get(f"/api/v1/wallet/topups/{t['id']}").status_code == 404
    assert post(s["client"], f"/api/v1/wallet/topups/{t['id']}/submit", {"payment_reference": "ref", "evidence_ref": "evidence"}).status_code == 403
    assert ok(s["client"].get("/api/v1/wallet/ledger"))["count"] == 0
    owner_a.tenant = s["tenant"]
    owner_a.save(update_fields=["tenant"])
    for name in ["Admin", "Sales", "Operations"]:
        role = Role.objects.create(tenant=s["tenant"], name=f"test-{name}", permissions_json=DEFAULT_ROLE_PERMISSIONS[name])
        owner_a.role = role
        owner_a.save(update_fields=["role"])
        assert s["client"].get("/api/v1/wallet").status_code == 403
        assert post(s["client"], "/api/v1/wallet/topups", {"amount_idr": 1}).status_code == 403
    owner_a.role = Role.objects.create(tenant=s["tenant"], name="Finance", permissions_json=DEFAULT_ROLE_PERMISSIONS["Finance"])
    owner_a.save(update_fields=["role"])
    assert s["client"].get("/api/v1/wallet").status_code == 200


def test_ledger_filters_csv_and_pagination(wallet_setup):
    s = wallet_setup
    ok(settle(s, topup(s)))
    with platform_tenant_context(s["tenant"].pk):
        atomic_debit(reference_id=uuid4(), amount_idr=1, description="=FORMULA()")
    assert ok(s["client"].get("/api/v1/wallet/ledger?kind=DEBIT"))["count"] == 1
    assert s["client"].get("/api/v1/wallet/ledger?from=not-date").status_code == 400
    assert s["client"].get("/api/v1/wallet/ledger?from=2026-02-30").status_code == 400
    assert s["client"].get("/api/v1/wallet/ledger?from=2026-1-1").status_code == 400
    assert s["client"].get("/api/v1/wallet/ledger?to=9999-12-31").status_code == 400
    assert s["client"].get("/api/v1/wallet/ledger?from=2026-12-01&to=2026-10-01").status_code == 400
    assert s["client"].get("/api/v1/wallet/ledger?kind=FORGED").status_code == 400
    assert s["client"].get("/api/v1/wallet/ledger?page=99").status_code == 404
    csv = s["client"].get("/api/v1/wallet/ledger/export?kind=DEBIT")
    assert csv.status_code == 200
    assert "'=FORMULA()" in csv.content.decode("utf-8-sig")
    assert "no-store" in csv["Cache-Control"]


def test_role_migration_preserves_custom_grants(wallet_setup):
    from django.apps import apps

    migration = import_module("modules.tenants.migrations.0007_wallet_role_defaults")
    tenant = wallet_setup["tenant"]
    normal = Role.objects.create(tenant=tenant, name="Finance", permissions_json=migration.BASELINE)
    custom = Role.objects.create(name="Finance", permissions_json=["payments.verify"])
    with connection.schema_editor() as editor:
        migration.upgrade(apps, editor)
    normal.refresh_from_db()
    custom.refresh_from_db()
    assert set(normal.permissions_json) == set(DEFAULT_ROLE_PERMISSIONS["Finance"])
    assert custom.permissions_json == ["payments.verify"]


def test_all_wallet_tables_have_rls(wallet_setup):
    with connection.cursor() as cursor:
        cursor.execute("SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(%s)", [["wallet_wallet", "wallet_walletledger", "wallet_wallettopup", "wallet_walletoperation", "wallet_walletevent", "wallet_walletreconciliation"]])
        rows = cursor.fetchall()
    assert len(rows) == 6 and all(enabled and forced for _, enabled, forced in rows)


def test_real_rls_without_superuser_on_every_wallet_table(wallet_setup, tenant_b):
    s = wallet_setup
    ok(settle(s, topup(s)))
    with platform_tenant_context(s["tenant"].pk):
        reconcile_wallet()
    role = "wallet_rls_" + uuid4().hex[:12]
    tables = ["wallet_wallet", "wallet_walletledger", "wallet_wallettopup", "wallet_walletoperation", "wallet_walletevent", "wallet_walletreconciliation"]
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
                    assert cursor.fetchone()[0] == expected, table
        finally:
            cursor.execute("RESET ROLE")


def test_platform_review_queue_and_suspended_user(wallet_setup):
    s = wallet_setup
    t = topup(s)
    url = f"/api/v1/platform/tenants/{s['tenant'].pk}/wallet/topups?status=PENDING"
    assert post(s["client"], url).status_code == 405
    assert s["client"].get(url).status_code == 403
    queue = ok(s["platform"].get(url))
    assert queue["count"] == 1 and queue["results"][0]["evidence_ref"] == t["evidence_ref"]
    s["owner"].status = "SUSPENDED"
    s["owner"].save(update_fields=["status"])
    assert s["client"].get("/api/v1/wallet").status_code == 403
    assert post(s["client"], "/api/v1/wallet/topups", {"amount_idr": 1}).status_code == 403


def test_csrf_and_anonymous_cannot_create_or_settle(wallet_setup):
    s = wallet_setup
    anonymous = Client()
    assert anonymous.get("/api/v1/wallet").status_code == 403
    t = topup(s)
    assert anonymous.post(f"/api/v1/platform/tenants/{s['tenant'].pk}/wallet/topups/{t['id']}/settle", {"amount_idr": 100_000, "provider_txn_id": "forged"}, content_type="application/json").status_code == 403
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(s["owner"])
    assert csrf.post("/api/v1/wallet/topups", {"amount_idr": 100_000}, content_type="application/json", HTTP_IDEMPOTENCY_KEY="no-csrf").status_code == 403


def test_db_rejects_cross_tenant_parent_and_changed_submitted_evidence(wallet_setup, tenant_b):
    s = wallet_setup
    t = topup(s)
    with platform_tenant_context(s["tenant"].pk):
        with pytest.raises(DatabaseError), transaction.atomic():
            WalletTopup.objects.filter(pk=t["id"]).update(evidence_ref="replaced")
        with pytest.raises(DatabaseError), transaction.atomic():
            WalletLedger.objects.create(tenant=tenant_b, wallet_id=WalletTopup.objects.get(pk=t["id"]).wallet_id, sequence=1, kind="DEBIT", signed_amount_idr=-1, balance_after_idr=0, reference_type="saas_charge", reference_id=uuid4(), description="forged")


def test_topup_stays_separate_from_travel_dp_and_s13_confirmation(wallet_setup, scenario):
    s = wallet_setup
    travel = scenario(environment="production")
    payment = ok(record(travel, amount=1))
    verified = ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify"))
    assert len([p for p in verified["participants"] if p["saas_charge_state"] == "pending_charge"]) == 1
    ok(settle(s, topup(s)))
    same_payment = ok(s["client"].get(f"/api/v1/payments/{payment['id']}"))
    assert same_payment["receipt"] == verified["receipt"]
    # S13: the settled top-up retries the pending charge once (PAY04); DP stays travel money.
    charged = [p for p in same_payment["participants"] if p["saas_charge_state"] == "charged"]
    assert len(charged) == 1 and charged[0]["status"] == "CONFIRMED" and charged[0]["saas_charge_status"] == "POSTED"
    invoice = ok(s["client"].get(f"/api/v1/invoices/{travel['invoice']['id']}"))
    assert invoice["paid_idr"] == 1
    assert balance(s)["balance_idr"] == 50_000


def test_demo_read_never_exposes_production_ledger(wallet_setup):
    s = wallet_setup
    t = topup(s)
    ok(settle(s, t))
    TenantEnvironment.objects.filter(tenant=s["tenant"]).update(state="READ_ONLY")
    TenantEnvironment.objects.create(tenant=s["tenant"], environment="demo", state="ACTIVE")
    assert balance(s)["balance_idr"] == 0
    assert ok(s["client"].get("/api/v1/wallet/ledger"))["count"] == 0
    assert ok(s["client"].get("/api/v1/wallet/topups"))["count"] == 0
    assert s["client"].get(f"/api/v1/wallet/topups/{t['id']}").status_code == 404
