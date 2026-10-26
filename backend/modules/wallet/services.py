"""All balance mutations lock the wallet first and append one source-unique entry.

Debits only come from S13 SaaS charges (`modules.billing`); there is
deliberately no tenant HTTP endpoint accepting an arbitrary debit.
"""
import hashlib
import json
import logging
from contextlib import contextmanager
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from modules.audit.services import log_event
from modules.tenants.context import clear_current_tenant, get_current_tenant, set_current_tenant
from modules.tenants.environment import assert_environment_writable, resolve_active_environment
from modules.tenants.models import Tenant
from modules.wallet.models import (
    MAX_BALANCE,
    Wallet,
    WalletEvent,
    WalletLedger,
    WalletOperation,
    WalletReconciliation,
    WalletTopup,
)

logger = logging.getLogger(__name__)
UNIT_PRICE_IDR = 50_000  # display estimate; charges snapshot SaaSPriceVersion


class Conflict(APIException):
    status_code = 409
    default_code = "wallet_conflict"


def production_tenant(*, writable=True):
    tenant = get_current_tenant()
    if tenant is None:
        raise PermissionDenied("Konteks tenant diperlukan.")
    if resolve_active_environment(tenant) != "production":
        raise PermissionDenied("Wallet SaaS nyata tersedia setelah workspace produksi diaktifkan.")
    if writable:
        assert_environment_writable(tenant, "production")
        if tenant.state not in {"ACTIVE", "RESTRICTED"}:
            raise PermissionDenied("Wallet tidak menerima perubahan pada status travel ini.")
    return tenant


def manual_instructions():
    values = {
        "bank_name": settings.WALLET_MANUAL_BANK_NAME.strip(),
        "account_name": settings.WALLET_MANUAL_ACCOUNT_NAME.strip(),
        "account_number": settings.WALLET_MANUAL_ACCOUNT_NUMBER.strip(),
    }
    return values if all(values.values()) else None


def positive_amount(amount):
    if type(amount) is not int or not 0 < amount <= 10_000_000_000:
        raise ValidationError({"amount_idr": "Nominal harus integer Rp1–Rp10 miliar."})


def locked_wallet():
    """Tenant lock serializes only lazy provisioning; mutations use wallet lock."""
    tenant = production_tenant()
    wallet = Wallet.objects.filter(tenant=tenant, currency="IDR").first()
    if wallet is None:
        Tenant.objects.select_for_update().get(pk=tenant.pk)
        wallet, _ = Wallet.objects.get_or_create(tenant=tenant, currency="IDR")
    return Wallet.objects.select_for_update().get(pk=wallet.pk)


def assert_active(wallet):
    if wallet.status != "ACTIVE":
        raise PermissionDenied("Wallet sedang dibekukan; hubungi dukungan platform.")


def _append(wallet, *, amount, kind, reference_type, reference_id, description, actor=None):
    balance = wallet.balance_cached_idr + amount
    if not 0 <= balance <= MAX_BALANCE:
        raise ValidationError({"amount_idr": "Saldo wallet di luar batas yang diizinkan."})
    # Caller holds wallet lock. A ledger-only mutation is never committed.
    entry = WalletLedger.objects.create(
        tenant=wallet.tenant, wallet=wallet, sequence=wallet.version + 1,
        kind=kind, signed_amount_idr=amount, balance_after_idr=balance,
        reference_type=reference_type, reference_id=reference_id,
        description=description, actor=actor,
    )
    wallet.balance_cached_idr = balance
    wallet.version += 1
    wallet.save(update_fields=["balance_cached_idr", "version", "updated_at"])
    return entry


@transaction.atomic
def create_topup(*, actor, amount_idr, key):
    positive_amount(amount_idr)
    if not isinstance(key, str) or not 1 <= len(key.strip()) <= 128:
        raise ValidationError({"Idempotency-Key": "Header wajib diisi, maksimal 128 karakter."})
    wallet = locked_wallet()
    digest = hashlib.sha256(json.dumps({"amount_idr": amount_idr}, sort_keys=True).encode()).hexdigest()
    existing = WalletOperation.objects.filter(key=key).select_related("topup").first()
    if existing:
        if existing.request_hash != digest:
            raise Conflict("Idempotency-Key telah dipakai untuk nominal lain.")
        return existing.topup
    assert_active(wallet)
    instructions = manual_instructions()
    if not instructions:
        raise ValidationError({"provider": "Rekening top-up platform belum dikonfigurasi. Hubungi dukungan."})
    topup = WalletTopup.objects.create(
        tenant=wallet.tenant, wallet=wallet, amount_idr=amount_idr,
        requested_by=actor, expires_at=timezone.now() + timedelta(hours=24),
        instructions_json=instructions,
    )
    WalletOperation.objects.create(tenant=wallet.tenant, key=key, request_hash=digest, topup=topup)
    log_event(action="wallet.topup.created", tenant=wallet.tenant, actor=actor, object_type="wallet_topup", object_id=topup.pk, changes={"amount_idr": amount_idr})
    return topup


def _topup(wallet, topup_id):
    topup = WalletTopup.objects.select_for_update().filter(pk=topup_id, wallet=wallet).first()
    if topup is None:
        raise NotFound("Top-up tidak ditemukan.")
    return topup


@transaction.atomic
def submit_topup(*, topup_id, actor, payment_reference, evidence_ref):
    wallet = locked_wallet()
    topup = _topup(wallet, topup_id)
    if topup.status == "PENDING":
        if (topup.payment_reference, topup.evidence_ref) != (payment_reference, evidence_ref):
            raise Conflict("Top-up sudah diajukan dengan bukti/referensi lain.")
        return topup
    assert_active(wallet)
    if topup.status != "CREATED":
        raise Conflict("Status top-up tidak dapat diajukan lagi.")
    if timezone.now() >= topup.expires_at:
        raise Conflict("Instruksi top-up kedaluwarsa. Hubungi dukungan bila dana sudah dikirim.")
    if not payment_reference.strip() or not evidence_ref.strip():
        raise ValidationError({"payment_reference": "Referensi dan lokasi bukti pembayaran wajib diisi."})
    topup.payment_reference = payment_reference
    topup.evidence_ref = evidence_ref
    topup.status = "PENDING"
    topup.save(update_fields=["payment_reference", "evidence_ref", "status", "updated_at"])
    log_event(action="wallet.topup.submitted", tenant=wallet.tenant, actor=actor, object_type="wallet_topup", object_id=topup.pk)
    return topup


def assert_platform_billing(actor):
    if not (actor.is_authenticated and actor.is_active and actor.status == "ACTIVE" and actor.email_verified_at and actor.is_staff and actor.has_perm("wallet.settle_topup")):
        raise PermissionDenied("Verifikasi settlement memerlukan petugas billing platform berizin.")


@contextmanager
def platform_tenant_context(tenant_id):
    """Only call after platform authorization; keep RLS scoped, including on exit."""
    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        raise NotFound("Travel tidak ditemukan.")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.tenant_id', true)")
            previous = cursor.fetchone()[0] or ""
            cursor.execute("SELECT set_config('app.tenant_id', %s, TRUE)", [str(tenant.pk)])
        token = set_current_tenant(tenant)
        try:
            yield tenant
        finally:
            clear_current_tenant(token)
            # A savepoint around the caller lets the outer transaction recover
            # before resetting RLS even when a financial constraint fails.
            if not connection.needs_rollback:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('app.tenant_id', %s, TRUE)", [previous])


@transaction.atomic
def settle_topup(*, tenant_id, topup_id, actor, amount_idr, provider_txn_id, decision="PAID", reason=""):
    assert_platform_billing(actor)
    positive_amount(amount_idr)
    if not provider_txn_id.strip() or len(provider_txn_id) > 160:
        raise ValidationError({"provider_txn_id": "Referensi transaksi bank wajib, maksimal 160 karakter."})
    if decision not in {"PAID", "REJECTED"}:
        raise ValidationError({"decision": "Pilih PAID atau REJECTED."})
    with platform_tenant_context(tenant_id):
        wallet = locked_wallet()
        topup = _topup(wallet, topup_id)
        if topup.requested_by_id == actor.pk:
            raise PermissionDenied("Petugas settlement harus berbeda dari pemohon top-up.")
        if topup.amount_idr != amount_idr:
            raise ValidationError({"amount_idr": "Nominal settlement tidak cocok dengan permintaan."})
        if topup.status == decision:
            if topup.provider_txn_id != provider_txn_id or (decision == "REJECTED" and topup.reason != reason):
                raise Conflict("Top-up sudah diproses dengan rincian settlement lain.")
            return topup
        if topup.status != "PENDING":
            raise Conflict("Settlement memerlukan bukti yang sudah diajukan (PENDING).")
        assert_active(wallet)
        if decision == "REJECTED" and not reason.strip():
            raise ValidationError({"reason": "Alasan penolakan wajib diisi."})
        # Bank funds can arrive after instruction expiry. PENDING requests do
        # not auto-expire; billing verifies actual settlement independently.
        try:
            with transaction.atomic():
                if decision == "PAID":
                    entry = _append(wallet, amount=topup.amount_idr, kind="TOPUP", reference_type="wallet_topup", reference_id=topup.pk, description=f"Top-up {topup.pk}", actor=actor)
                    topup.ledger_entry = entry
                    topup.paid_at = timezone.now()
                topup.status = decision
                topup.provider_txn_id = provider_txn_id
                topup.settled_by = actor
                topup.reason = reason
                topup.save(update_fields=["status", "provider_txn_id", "settled_by", "reason", "ledger_entry", "paid_at", "updated_at"])
                if decision == "PAID":
                    WalletEvent.objects.create(tenant=wallet.tenant, topup=topup, payload_json={"wallet_id": str(wallet.pk), "topup_id": str(topup.pk), "amount_idr": topup.amount_idr})
        except IntegrityError:
            raise Conflict("Referensi settlement bank sudah digunakan atau ledger tidak konsisten.") from None
        log_event(action=f"wallet.topup.{decision.lower()}", tenant=wallet.tenant, actor=actor, object_type="wallet_topup", object_id=topup.pk, changes={"amount_idr": amount_idr, "reason": reason})
        if decision == "PAID":
            from modules.billing.services import settle_pending_charges

            # Spec §9.3: a settled top-up retries pending charges FIFO under the
            # same wallet lock. A retry failure never undoes the bank credit.
            try:
                with transaction.atomic():
                    settle_pending_charges(wallet)
            except DatabaseError:
                logger.exception("pending_charge_retry_failed", extra={"wallet_id": str(wallet.pk)})
        return topup


def debit_locked(wallet, *, reference_id, amount_idr, description, actor=None):
    """Caller holds the wallet lock. None on insufficient funds; never overdraws."""
    positive_amount(amount_idr)
    if not isinstance(description, str) or not 1 <= len(description) <= 240:
        raise ValidationError({"description": "Deskripsi wajib, maksimal 240 karakter."})
    previous = WalletLedger.objects.filter(wallet=wallet, kind="DEBIT", reference_type="saas_charge", reference_id=reference_id).first()
    if previous:
        if previous.signed_amount_idr != -amount_idr or previous.description != description:
            raise Conflict("Referensi charge telah digunakan untuk rincian lain.")
        return previous
    assert_active(wallet)
    if wallet.balance_cached_idr < amount_idr:
        return None
    entry = _append(wallet, amount=-amount_idr, kind="DEBIT", reference_type="saas_charge", reference_id=reference_id, description=description, actor=actor)
    log_event(action="wallet.debited", tenant=wallet.tenant, actor=actor, object_type="wallet_ledger", object_id=entry.pk, changes={"amount_idr": amount_idr, "reference_id": str(reference_id)})
    return entry


def refund_credit_locked(wallet, *, adjustment, actor):
    """Compensating credit for an approved SaaS adjustment; caller holds the wallet lock."""
    assert_active(wallet)
    entry = _append(wallet, amount=adjustment.amount_idr, kind="REFUND", reference_type="saas_adjustment", reference_id=adjustment.pk, description=f"Refund SaaS {adjustment.charge_id}", actor=actor)
    log_event(action="wallet.refund_credited", tenant=wallet.tenant, actor=actor, object_type="wallet_ledger", object_id=entry.pk, changes={"amount_idr": adjustment.amount_idr, "adjustment_id": str(adjustment.pk)})
    return entry


@transaction.atomic
def atomic_debit(*, reference_id, amount_idr, description="Biaya SaaS", actor=None):
    """Locking wrapper around `debit_locked`; reference must be a charge UUID.

    A debit without a matching SaaSCharge is reported by reconciliation.
    """
    positive_amount(amount_idr)
    try:
        reference_id = UUID(str(reference_id))
    except ValueError:
        raise ValidationError({"reference_id": "UUID charge diperlukan."}) from None
    return debit_locked(locked_wallet(), reference_id=reference_id, amount_idr=amount_idr, description=description, actor=actor)


@transaction.atomic
def reconcile_wallet():
    """Capture a stable snapshot. Detect, never silently rewrite discrepancies."""
    production_tenant(writable=False)
    wallet = Wallet.objects.select_for_update().first()
    if wallet is None:
        return None
    rows = wallet.ledger.order_by("sequence")
    balance = 0
    count = 0
    chain_ok = True
    for entry in rows.iterator():
        count += 1
        balance += entry.signed_amount_idr
        chain_ok &= entry.sequence == count and entry.balance_after_idr == balance and entry.tenant_id == wallet.tenant_id
    variance = wallet.balance_cached_idr - balance
    # Check paid top-ups have exactly their own matching credit and amount.
    paid = WalletTopup.objects.filter(wallet=wallet, status="PAID").select_related("ledger_entry")
    topups_ok = all(t.ledger_entry.wallet_id == wallet.pk and t.ledger_entry.tenant_id == wallet.tenant_id and t.ledger_entry.kind == "TOPUP" and t.ledger_entry.reference_id == t.pk and t.ledger_entry.signed_amount_idr == t.amount_idr for t in paid)
    topups_ok &= WalletLedger.objects.filter(wallet=wallet, kind="TOPUP").count() == paid.count()
    charges = charge_checks(wallet)
    consistent = bool(variance == 0 and chain_ok and topups_ok and charges["charges_ok"] and charges["refunds_ok"] and wallet.version == count and balance >= 0)
    result = WalletReconciliation.objects.create(
        tenant=wallet.tenant, wallet=wallet, cached_balance_idr=wallet.balance_cached_idr,
        ledger_balance_idr=balance, variance_idr=variance, ledger_count=count, consistent=consistent,
        details_json={"chain_ok": bool(chain_ok), "topups_ok": bool(topups_ok), "wallet_version": wallet.version, **charges},
    )
    if not consistent:
        logger.error("wallet_reconciliation_mismatch", extra={"wallet_id": str(wallet.pk), "variance_idr": variance})
        log_event(action="wallet.reconciliation.mismatch", tenant=wallet.tenant, object_type="wallet", object_id=wallet.pk, changes={"variance_idr": variance, "chain_ok": bool(chain_ok), "topups_ok": bool(topups_ok), **charges})
    return result


def charge_checks(wallet):
    """Every DEBIT belongs to one posted charge and every REFUND to one approved credit."""
    from modules.billing.models import SaaSAdjustment, SaaSCharge

    posted = SaaSCharge.objects.filter(wallet=wallet, status__in=["POSTED", "REFUNDED"]).select_related("ledger_entry")
    charges_ok = all(c.ledger_entry.wallet_id == wallet.pk and c.ledger_entry.kind == "DEBIT" and c.ledger_entry.reference_id == c.pk and c.ledger_entry.signed_amount_idr == -c.unit_price_idr for c in posted)
    orphan_debits = WalletLedger.objects.filter(wallet=wallet, kind="DEBIT").count() - posted.count()
    approved = SaaSAdjustment.objects.filter(status="APPROVED", charge__wallet=wallet).select_related("ledger_entry", "charge")
    refunds_ok = all(a.ledger_entry.wallet_id == wallet.pk and a.ledger_entry.kind == "REFUND" and a.ledger_entry.reference_id == a.pk and a.ledger_entry.signed_amount_idr == a.amount_idr == a.charge.unit_price_idr and a.charge.status == "REFUNDED" for a in approved)
    orphan_refunds = WalletLedger.objects.filter(wallet=wallet, kind="REFUND").count() - approved.count()
    return {
        "charges_ok": bool(charges_ok and orphan_debits == 0), "orphan_debits": orphan_debits,
        "refunds_ok": bool(refunds_ok and orphan_refunds == 0), "orphan_refunds": orphan_refunds,
        "pending_charges": SaaSCharge.objects.filter(status="PENDING").count(),
    }


def ledger_total(wallet):
    return wallet.ledger.aggregate(value=Sum("signed_amount_idr"))["value"] or 0
