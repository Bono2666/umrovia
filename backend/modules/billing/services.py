"""S13: DP terverifikasi → charge SaaS tepat sekali per booking-jamaah.

Urutan lock global: wallet → booking → payment/invoice → peserta (urut id) →
charge → tenant. Setiap jalur yang menyentuh saldo mengambil wallet lebih
dulu (verifikasi DP, retry setelah top-up, keputusan refund), sehingga
semuanya terserialisasi per tenant. Jalur tanpa wallet (reversal DP,
pembatalan booking) hanya mem-VOID charge PENDING dengan urutan yang sama.

Saldo kurang tidak pernah menggagalkan verifikasi DP (Spec §8 "verification
still succeeds"): charge tetap PENDING, peserta `pending_charge`, tenant
RESTRICTED sampai antrean FIFO lunas.
"""
import logging
from datetime import UTC, datetime

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from modules.audit.services import log_event
from modules.billing.models import BillingEvent, SaaSAdjustment, SaaSCharge, SaaSPriceVersion
from modules.booking.models import BookingParticipant
from modules.tenants.models import Tenant
from modules.wallet.models import Wallet
from modules.wallet.services import (
    assert_active,
    debit_locked,
    platform_tenant_context,
    production_tenant,
    refund_credit_locked,
)

logger = logging.getLogger(__name__)
RETRY_BATCH = 200
STANDARD_PRICE = {"code": "STD-2026", "unit_price_idr": 50_000, "effective_from": datetime(2026, 1, 1, tzinfo=UTC)}


class Conflict(APIException):
    status_code = 409
    default_code = "billing_conflict"


def current_price():
    price = SaaSPriceVersion.objects.filter(effective_from__lte=timezone.now()).order_by("-effective_from").first()
    if price is None:
        # POL-02 standard (also seeded by migration). A missing row must never
        # block DP verification, so restore the approved default version.
        price, _ = SaaSPriceVersion.objects.get_or_create(code=STANDARD_PRICE["code"], defaults=STANDARD_PRICE)
    return price


def lock_wallet(tenant):
    """Kunci wallet produksi tanpa provisioning; tidak ada wallet = saldo nol."""
    return Wallet.objects.select_for_update().filter(tenant=tenant, currency="IDR").first()


def _event(tenant, kind, dedupe_key, payload):
    BillingEvent.objects.get_or_create(tenant=tenant, dedupe_key=dedupe_key, defaults={"kind": kind, "payload_json": payload})


def _charge_payload(charge, participant):
    return {"charge_id": str(charge.pk), "booking_id": str(charge.booking_id), "booking_passenger_id": str(participant.booking_passenger_id), "unit_price_idr": charge.unit_price_idr}


def _sync_restriction(tenant):
    """RESTRICTED = ada charge tertunda (Spec §6.1), bukan blokir pengguna."""
    pending = SaaSCharge.objects.filter(status="PENDING").exists()
    source, target = ("ACTIVE", "RESTRICTED") if pending else ("RESTRICTED", "ACTIVE")
    if Tenant.objects.filter(pk=tenant.pk, state=source).update(state=target):
        tenant.state = target
        log_event(action=f"tenant.billing.{target.lower()}", tenant=tenant, object_type="tenant", object_id=tenant.pk, changes={"state": target})


def _open_charge(participant, payment):
    charge = SaaSCharge.objects.select_for_update().filter(participant=participant).exclude(status="VOID").first()
    if charge:
        return charge
    price = current_price()
    charge = SaaSCharge.objects.create(
        tenant_id=participant.tenant_id, participant=participant, booking_id=participant.booking_id,
        source_payment=payment, unit_price_idr=price.unit_price_idr, price_version=price,
        eligible_at=participant.dp_eligible_at or timezone.now(),
    )
    log_event(action="saas.charge.created", tenant=payment.tenant, object_type="saas_charge", object_id=charge.pk, changes={"unit_price_idr": charge.unit_price_idr, "price_version": price.code})
    return charge


def _mark_pending(charge, participant, reason, *, attempted):
    fields = ["pending_reason", "updated_at"]
    if attempted:
        charge.attempts += 1
        charge.last_attempt_at = timezone.now()
        fields += ["attempts", "last_attempt_at"]
    elif charge.pending_reason == reason:
        return
    charge.pending_reason = reason
    charge.save(update_fields=fields)
    if participant.saas_charge_state != "pending_charge":
        participant.saas_charge_state = "pending_charge"
        participant.save(update_fields=["saas_charge_state", "updated_at"])
    # Satu alert per charge (= peserta + epoch pending), Spec §11 dedupe.
    _event(charge.tenant, "saas.charge.pending", f"saas.charge.pending:{charge.pk}", {**_charge_payload(charge, participant), "reason": reason})
    from modules.notifications.services import charge_pending

    charge_pending(charge, participant, reason)


def _post(charge, participant, wallet, actor):
    description = f"Biaya SaaS booking-jamaah {participant.booking_passenger_id}"
    entry = debit_locked(wallet, reference_id=charge.pk, amount_idr=charge.unit_price_idr, description=description, actor=actor)
    if entry is None:
        return False
    charge.attempts += 1
    charge.status, charge.wallet, charge.ledger_entry = "POSTED", wallet, entry
    charge.charged_at = charge.last_attempt_at = timezone.now()
    charge.pending_reason = ""
    charge.save(update_fields=["status", "wallet", "ledger_entry", "charged_at", "attempts", "last_attempt_at", "pending_reason", "updated_at"])
    participant.saas_charge_state = "charged"
    if participant.participant_status == "DP_VERIFIED_PENDING_CHARGE":
        participant.participant_status = "CONFIRMED"
    participant.save(update_fields=["saas_charge_state", "participant_status", "updated_at"])
    _event(charge.tenant, "saas.charge.posted", f"saas.charge.posted:{charge.pk}", {**_charge_payload(charge, participant), "ledger_entry_id": str(entry.pk)})
    log_event(action="saas.charge.posted", tenant=charge.tenant, actor=actor, object_type="saas_charge", object_id=charge.pk, changes={"unit_price_idr": charge.unit_price_idr, "ledger_entry_id": str(entry.pk)})
    return True


def _void(charge, participant, reason):
    charge.status, charge.void_reason, charge.pending_reason = "VOID", reason[:240], ""
    charge.save(update_fields=["status", "void_reason", "pending_reason", "updated_at"])
    if participant.saas_charge_state == "pending_charge":
        participant.saas_charge_state = "not_eligible"
        participant.save(update_fields=["saas_charge_state", "updated_at"])
    log_event(action="saas.charge.voided", tenant=charge.tenant, object_type="saas_charge", object_id=charge.pk, changes={"reason": reason})


def settle_pending_charges(wallet, *, actor=None, limit=RETRY_BATCH):
    """FIFO menurut eligible_at; caller memegang lock wallet (boleh None).

    Peserta dikunci urut id sebelum charge agar sejalan dengan reversal dan
    pembatalan booking. Begitu satu charge tidak dapat diposting, sisanya
    ikut menunggu (FIFO ketat; tarif lama tidak dilangkahi tarif baru).
    """
    result = {"posted": 0, "pending": 0, "voided": 0}
    candidates = list(SaaSCharge.objects.filter(status="PENDING").order_by("eligible_at", "id").values_list("pk", "participant_id")[:limit])
    if candidates:
        participants = {p.pk: p for p in BookingParticipant.objects.select_for_update().filter(pk__in=[pid for _, pid in candidates]).order_by("id")}
        charges = {c.pk: c for c in SaaSCharge.objects.select_for_update().filter(pk__in=[cid for cid, _ in candidates]).select_related("tenant").order_by("id")}
        tenant = next(iter(charges.values())).tenant
        blocked = ""
        if wallet is None:
            blocked = "INSUFFICIENT_FUNDS"
        elif wallet.status != "ACTIVE" or tenant.state not in {"ACTIVE", "RESTRICTED"}:
            blocked = "WALLET_UNAVAILABLE"
        for charge_id, participant_id in candidates:
            charge, participant = charges[charge_id], participants[participant_id]
            if charge.status != "PENDING":
                continue
            if participant.participant_status == "CANCELED" or participant.dp_eligible_at is None:
                _void(charge, participant, "Peserta tidak lagi memenuhi syarat DP.")
                result["voided"] += 1
                continue
            if not blocked and _post(charge, participant, wallet, actor):
                result["posted"] += 1
                continue
            attempted = not blocked
            blocked = blocked or "INSUFFICIENT_FUNDS"
            _mark_pending(charge, participant, blocked, attempted=attempted)
            result["pending"] += 1
        _sync_restriction(tenant)
    else:
        tenant = wallet.tenant if wallet else None
        if tenant:
            _sync_restriction(tenant)
    if any(result.values()):
        logger.info("saas_pending_charges_settled", extra=result)
    return result


def charge_verified_booking(*, booking, payment, actor):
    """Dipanggil verify_payment produksi; wallet sudah dikunci sebelum booking."""
    wallet = lock_wallet(booking.tenant)
    rows = BookingParticipant.objects.select_for_update().filter(booking=booking, dp_eligible_at__isnull=False, saas_charge_state="pending_charge").exclude(participant_status="CANCELED").order_by("id")
    for participant in rows:
        _open_charge(participant, payment)
    return settle_pending_charges(wallet, actor=actor)


def void_pending_for_booking(booking, reason):
    """Reversal/pembatalan: peserta yang tidak lagi eligible tidak ditagih.

    Charge POSTED tidak pernah dibalik otomatis (Spec §7.5, PAY09).
    """
    rows = list(BookingParticipant.objects.select_for_update().filter(booking=booking).order_by("id"))
    ineligible = {p.pk: p for p in rows if p.participant_status == "CANCELED" or p.dp_eligible_at is None}
    voided = 0
    for charge in SaaSCharge.objects.select_for_update().filter(booking=booking, status="PENDING", participant_id__in=list(ineligible)).order_by("id"):
        _void(charge, ineligible[charge.participant_id], reason)
        voided += 1
    if voided:
        _sync_restriction(booking.tenant)
    return voided


@transaction.atomic
def retry_pending_charges(*, actor=None):
    return settle_pending_charges(lock_wallet(production_tenant()), actor=actor)


def charge_status(charge):
    if charge is None:
        return None
    return f"PENDING_{charge.pending_reason or 'INSUFFICIENT_FUNDS'}" if charge.status == "PENDING" else charge.status


def charge_preview(payment, *, show_wallet):
    """Pratinjau sebelum verifikasi (Spec §4.3): peserta, tarif, saldo, sudah ditagih."""
    if payment.environment != "production":
        return {"environment": payment.environment, "charges_applicable": False, "participants": []}
    price = current_price()
    rows = []
    for allocation in payment.allocations.select_related("participant__pilgrim").order_by("participant_id"):
        participant = allocation.participant
        charge = participant.saas_charges.exclude(status="VOID").first()
        already = participant.saas_charge_state in {"charged", "waived"} or (charge is not None and charge.status != "PENDING")
        will_charge = not already and participant.participant_status != "CANCELED"
        rows.append({
            "booking_participant_id": str(participant.pk), "pilgrim_name": participant.pilgrim.name,
            "allocation_idr": allocation.amount_idr, "already_charged": already, "will_attempt_charge": will_charge,
            "unit_fee_idr": charge.unit_price_idr if charge else price.unit_price_idr if will_charge else 0,
        })
    total = sum(row["unit_fee_idr"] for row in rows if row["will_attempt_charge"])
    preview = {"environment": "production", "charges_applicable": True, "price_version": price.code, "unit_fee_idr": price.unit_price_idr, "participants": rows, "total_fee_idr": total}
    if show_wallet:
        wallet = Wallet.objects.filter(currency="IDR").first()
        balance = wallet.balance_cached_idr if wallet else 0
        own = {row["booking_participant_id"] for row in rows}
        queued = sum(c.unit_price_idr for c in SaaSCharge.objects.filter(status="PENDING").exclude(participant_id__in=own))
        preview.update({"wallet_balance_idr": balance, "pending_queue_idr": queued, "balance_after_idr": balance - queued - total, "sufficient": balance - queued >= total})
    return preview


@transaction.atomic
def request_refund(*, charge_id, actor, reason):
    reason = (reason or "").strip()
    if not 5 <= len(reason) <= 2000:
        raise ValidationError({"reason": "Alasan refund wajib, 5–2000 karakter."})
    production_tenant()
    charge = SaaSCharge.objects.select_for_update().filter(pk=charge_id).select_related("participant").first()
    if charge is None:
        raise NotFound("Charge tidak ditemukan.")
    existing = charge.adjustments.filter(status__in=["REQUESTED", "APPROVED"]).first()
    if existing:
        if existing.reason == reason and existing.requested_by_id == actor.pk:
            return existing
        raise Conflict("Permintaan refund untuk charge ini sudah ada.")
    if charge.status != "POSTED":
        raise ValidationError({"charge": "Refund hanya untuk charge yang sudah diposting."})
    if charge.participant.participant_status != "CANCELED":
        raise ValidationError({"charge": "Refund SaaS hanya dapat diajukan untuk peserta yang dibatalkan."})
    adjustment = SaaSAdjustment.objects.create(tenant=charge.tenant, charge=charge, amount_idr=charge.unit_price_idr, reason=reason, requested_by=actor)
    _event(charge.tenant, "saas.refund.requested", f"saas.refund.requested:{adjustment.pk}", {"adjustment_id": str(adjustment.pk), "charge_id": str(charge.pk), "amount_idr": adjustment.amount_idr})
    log_event(action="saas.refund.requested", tenant=charge.tenant, actor=actor, object_type="saas_adjustment", object_id=adjustment.pk, changes={"charge_id": str(charge.pk), "reason": reason})
    return adjustment


def assert_platform_refund(actor):
    if not (actor.is_authenticated and actor.is_active and actor.status == "ACTIVE" and actor.email_verified_at and actor.is_staff and actor.has_perm("billing.approve_adjustment")):
        raise PermissionDenied("Keputusan refund memerlukan petugas billing platform berizin.")


@transaction.atomic
def decide_refund(*, tenant_id, adjustment_id, actor, decision, reason):
    assert_platform_refund(actor)
    reason = (reason or "").strip()
    if decision not in {"APPROVED", "REJECTED"}:
        raise ValidationError({"decision": "Pilih APPROVED atau REJECTED."})
    if not reason:
        raise ValidationError({"reason": "Alasan keputusan wajib diisi."})
    with platform_tenant_context(tenant_id) as tenant:
        wallet = lock_wallet(tenant)
        adjustment = SaaSAdjustment.objects.select_for_update().filter(pk=adjustment_id).first()
        if adjustment is None:
            raise NotFound("Permintaan refund tidak ditemukan.")
        if adjustment.requested_by_id == actor.pk:
            raise PermissionDenied("Pemutus refund harus berbeda dari pemohon.")
        if adjustment.status == decision:
            if adjustment.decision_reason != reason:
                raise Conflict("Refund sudah diputuskan dengan alasan lain.")
            return adjustment
        if adjustment.status != "REQUESTED":
            raise Conflict("Permintaan refund sudah diputuskan.")
        participant = BookingParticipant.objects.select_for_update().get(pk=SaaSCharge.objects.get(pk=adjustment.charge_id).participant_id)
        charge = SaaSCharge.objects.select_for_update().get(pk=adjustment.charge_id)
        fields = ["status", "approver", "decision_reason", "decided_at", "updated_at"]
        if decision == "APPROVED":
            if charge.status != "POSTED" or wallet is None or charge.wallet_id != wallet.pk:
                raise Conflict("Charge tidak lagi dapat direfund.")
            assert_active(wallet)
            adjustment.ledger_entry = refund_credit_locked(wallet, adjustment=adjustment, actor=actor)
            fields.append("ledger_entry")
        adjustment.status, adjustment.approver, adjustment.decision_reason = decision, actor, reason
        adjustment.decided_at = timezone.now()
        adjustment.save(update_fields=fields)
        if decision == "APPROVED":
            # Database guard: REFUNDED requires the approved credit saved first.
            charge.status = "REFUNDED"
            charge.save(update_fields=["status", "updated_at"])
            participant.saas_charge_state = "reversed"
            participant.save(update_fields=["saas_charge_state", "updated_at"])
        _event(tenant, f"saas.refund.{decision.lower()}", f"saas.refund.decided:{adjustment.pk}", {"adjustment_id": str(adjustment.pk), "charge_id": str(charge.pk), "amount_idr": adjustment.amount_idr, "decision": decision})
        log_event(action=f"saas.refund.{decision.lower()}", tenant=tenant, actor=actor, object_type="saas_adjustment", object_id=adjustment.pk, changes={"amount_idr": adjustment.amount_idr, "reason": reason})
        if decision == "APPROVED":
            settle_pending_charges(wallet)
        return adjustment
