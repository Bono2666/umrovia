"""Layanan agen & komisi (PRD MOD-10, §7.3; UAT-09/UAT-10).

Urutan lock mengikuti S11: booking → invoice → komisi. `sync_commission`
dipanggil dari transaksi pemanggil (reservasi, verifikasi/reversal
pembayaran, revisi invoice, ganti agen, pembatalan) dan idempoten.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from modules.agents.models import (
    Agent,
    BookingAgentChange,
    Commission,
    CommissionKind,
    CommissionPolicy,
    CommissionStatus,
    CommissionTrigger,
    generate_agent_code,
)
from modules.audit.services import log_event
from modules.payments.dates import tenant_today

OPEN_STATUSES = [CommissionStatus.ESTIMATED, CommissionStatus.ELIGIBLE]
INACTIVE_BOOKINGS = {"CANCELED", "EXPIRED"}


def _actor(actor):
    return actor if getattr(actor, "is_authenticated", False) else None


# ---------------------------------------------------------------- master agen
def create_agent(*, tenant, environment, data, actor):
    for _attempt in range(3):
        code = (data.get("code") or "").strip().upper() or generate_agent_code()
        try:
            with transaction.atomic():
                agent = Agent.objects.create(tenant=tenant, environment=environment, **{**data, "code": code})
            break
        except IntegrityError:
            if data.get("code"):
                raise ValidationError({"code": "Kode agen sudah dipakai."}) from None
    else:
        raise ValidationError({"code": "Gagal membuat kode agen, coba lagi."})
    log_event(action="agents.created", tenant=tenant, actor=_actor(actor), object_type="agent", object_id=agent.pk, changes={"code": agent.code, "name": agent.name})
    return agent


def update_agent(*, agent, data, actor):
    if "code" in data:
        data["code"] = data["code"].strip().upper()
        if Agent.objects.filter(environment=agent.environment, code=data["code"]).exclude(pk=agent.pk).exists():
            raise ValidationError({"code": "Kode agen sudah dipakai."})
    for key, value in data.items():
        setattr(agent, key, value)
    agent.save()
    log_event(action="agents.updated", tenant=agent.tenant, actor=_actor(actor), object_type="agent", object_id=agent.pk, changes={"fields": sorted(data)})
    return agent


# ----------------------------------------------------------- booking ↔ agen
def assign_agent(*, booking, agent_id, actor, reason=""):
    """Set agen booking + histori. Komisi disinkronkan (no-op selama DRAFT)."""
    agent = None
    if agent_id:
        agent = Agent.objects.filter(pk=agent_id, environment=booking.environment).first()
        if agent is None:
            raise ValidationError({"agent": "Agen tidak ditemukan."})
        if not agent.active and agent.pk != booking.agent_id:
            raise ValidationError({"agent": "Agen tidak aktif."})
    if (agent.pk if agent else None) == booking.agent_id:
        return booking
    BookingAgentChange.objects.create(
        tenant=booking.tenant, environment=booking.environment, booking=booking,
        from_agent_id=booking.agent_id, to_agent=agent, reason=(reason or "").strip()[:240], changed_by=_actor(actor),
    )
    booking.agent = agent
    booking.save(update_fields=["agent", "updated_at"])
    return booking


@transaction.atomic
def change_booking_agent(*, booking_id, agent_id, reason, actor):
    from modules.booking.models import Booking

    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if booking.status in INACTIVE_BOOKINGS | {"COMPLETED"}:
        raise ValidationError({"booking": "Agen hanya dapat diubah pada booking yang masih aktif."})
    if booking.status != "DRAFT" and not (reason or "").strip():
        raise ValidationError({"reason": "Alasan perubahan agen wajib diisi."})
    locked = Commission.objects.select_for_update().filter(booking=booking, status__in=[CommissionStatus.APPROVED, CommissionStatus.PAID]).first()
    if locked:
        raise ValidationError({"agent": f"Komisi booking ini sudah {locked.get_status_display().lower()}; batalkan komisi terlebih dahulu."})
    previous = booking.agent_id
    assign_agent(booking=booking, agent_id=agent_id, actor=actor, reason=reason)
    if booking.agent_id != previous:
        sync_commission(booking, reason="Agen booking diganti")
        log_event(action="bookings.agent_changed", tenant=booking.tenant, actor=_actor(actor), object_type="booking", object_id=booking.pk, changes={"from": str(previous) if previous else None, "to": str(booking.agent_id) if booking.agent_id else None, "reason": reason})
    return booking


# ------------------------------------------------------------ kebijakan
def resolve_policy(booking, on_date):
    """Kebijakan aktif paling spesifik: agen+paket > agen > paket > umum."""
    package_id = booking.departure.package_id
    candidates = CommissionPolicy.objects.filter(environment=booking.environment, active=True).filter(
        Q(agent_id=booking.agent_id) | Q(agent__isnull=True), Q(package_id=package_id) | Q(package__isnull=True),
        Q(valid_from__isnull=True) | Q(valid_from__lte=on_date), Q(valid_until__isnull=True) | Q(valid_until__gte=on_date),
    )
    ranked = sorted(candidates, key=lambda p: (p.agent_id is not None, p.package_id is not None, p.created_at), reverse=True)
    return ranked[0] if ranked else None


def policy_snapshot(policy):
    return {
        "id": str(policy.pk), "name": policy.name, "kind": policy.kind, "amount_idr": policy.amount_idr,
        "percent": str(policy.percent), "trigger": policy.trigger, "captured_at": timezone.now().isoformat(),
    }


def compute_amount(snapshot, *, pax, basis):
    if snapshot["kind"] == CommissionKind.FIXED_PER_PAX:
        return int(snapshot["amount_idr"]) * pax
    return int((Decimal(basis) * Decimal(snapshot["percent"]) / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _basis(booking):
    from modules.booking.services import participant_net

    rows = [p for p in booking.participants.all() if p.participant_status != "CANCELED"]
    return len(rows), sum(participant_net(p.pricing_snapshot_json) for p in rows)


def _eligible(booking, trigger):
    from modules.payments.models import TravelInvoice

    invoice = TravelInvoice.objects.filter(booking=booking).exclude(status="VOIDED").first()
    if invoice is None:
        return False
    if trigger == CommissionTrigger.FULLY_PAID:
        return invoice.status == "PAID"
    return invoice.total_idr - invoice.balance_idr > 0


def sync_commission(booking, *, reason=""):
    """Selaraskan komisi dengan keadaan booking (idempoten, dalam transaksi pemanggil)."""
    active = Commission.objects.select_for_update().filter(booking=booking).exclude(status=CommissionStatus.REVERSED).first()
    now = timezone.now()
    if booking.status in INACTIVE_BOOKINGS:
        if active is None:
            return None
        if active.status == CommissionStatus.PAID:
            active.review_note = f"Booking dibatalkan setelah komisi dibayar: {reason}"[:240]
            active.save(update_fields=["review_note", "updated_at"])
            return active
        return _reverse(active, f"Booking {booking.get_status_display().lower()}: {reason}", now)
    if booking.status == "DRAFT":
        return None
    if active is not None and active.agent_id != booking.agent_id:
        _reverse(active, reason or "Agen booking diganti", now)
        active = None
    if booking.agent_id is None:
        return None
    pax, basis = _basis(booking)
    if active is None:
        if Commission.objects.filter(booking=booking, agent_id=booking.agent_id, status=CommissionStatus.REVERSED, reversed_by__isnull=False).exists():
            return None  # dibatalkan manual oleh finance: jangan dibuat ulang otomatis
        policy = resolve_policy(booking, tenant_today(booking.tenant))
        if policy is None:
            return None
        snapshot = policy_snapshot(policy)
        active = Commission.objects.create(
            tenant=booking.tenant, environment=booking.environment, booking=booking, agent_id=booking.agent_id,
            policy=policy, policy_snapshot_json=snapshot, pax=pax, basis_idr=basis, amount_idr=compute_amount(snapshot, pax=pax, basis=basis),
        )
    if active.status not in OPEN_STATUSES:
        return active
    active.pax, active.basis_idr = pax, basis
    active.amount_idr = compute_amount(active.policy_snapshot_json, pax=pax, basis=basis)
    eligible = _eligible(booking, active.policy_snapshot_json["trigger"])
    if eligible and active.status == CommissionStatus.ESTIMATED:
        active.status, active.eligible_at = CommissionStatus.ELIGIBLE, now
    elif not eligible and active.status == CommissionStatus.ELIGIBLE:
        active.status, active.eligible_at = CommissionStatus.ESTIMATED, None
    active.save(update_fields=["pax", "basis_idr", "amount_idr", "status", "eligible_at", "updated_at"])
    return active


def _reverse(commission, reason, now):
    commission.status, commission.reversed_at, commission.reverse_reason = CommissionStatus.REVERSED, now, (reason or "Dibatalkan")[:240]
    commission.save(update_fields=["status", "reversed_at", "reverse_reason", "updated_at"])
    return commission


# ------------------------------------------------------------ siklus komisi
def _lock(commission_id):
    from modules.booking.models import Booking

    initial = Commission.objects.get(pk=commission_id)
    Booking.objects.select_for_update().get(pk=initial.booking_id)
    return Commission.objects.select_for_update().select_related("agent", "booking__departure").get(pk=commission_id)


@transaction.atomic
def approve_commission(*, commission_id, actor, note=""):
    commission = _lock(commission_id)
    if commission.status == CommissionStatus.APPROVED:
        return commission
    if commission.status != CommissionStatus.ELIGIBLE:
        raise ValidationError({"status": "Hanya komisi berstatus layak dibayar yang dapat disetujui."})
    if commission.amount_idr < 1:
        raise ValidationError({"amount_idr": "Nilai komisi Rp0 tidak perlu disetujui."})
    commission.status, commission.approved_at, commission.approved_by = CommissionStatus.APPROVED, timezone.now(), actor
    commission.save(update_fields=["status", "approved_at", "approved_by", "updated_at"])
    log_event(action="commissions.approved", tenant=commission.tenant, actor=actor, object_type="commission", object_id=commission.pk, changes={"amount_idr": commission.amount_idr, "note": note})
    return commission


@transaction.atomic
def pay_commission(*, commission_id, actor, paid_on, bank_account=None, reference=""):
    from modules.travel_finance.models import ExpenseCategory, TravelBankAccount, TravelExpense

    commission = _lock(commission_id)
    if commission.status == CommissionStatus.PAID:
        return commission
    if commission.status != CommissionStatus.APPROVED:
        raise ValidationError({"status": "Komisi harus disetujui sebelum dibayar."})
    if paid_on > tenant_today(commission.tenant):
        raise ValidationError({"paid_on": "Tanggal bayar tidak boleh di masa depan."})
    if bank_account is not None:
        bank_account = TravelBankAccount.objects.filter(pk=bank_account.pk, active=True).first()
        if bank_account is None:
            raise ValidationError({"bank_account": "Rekening tidak aktif."})
    booking = commission.booking
    expense = TravelExpense.objects.create(
        tenant=commission.tenant, environment=commission.environment, spent_on=paid_on, category=ExpenseCategory.COMMISSION,
        amount_idr=commission.amount_idr, departure=booking.departure, bank_account=bank_account,
        description=f"Komisi {commission.agent.code} {commission.agent.name} · {booking.code}"[:240], reference=(reference or "").strip()[:120], created_by=actor,
    )
    commission.status, commission.paid_on, commission.paid_by = CommissionStatus.PAID, paid_on, actor
    commission.bank_account, commission.reference, commission.expense = bank_account, (reference or "").strip()[:120], expense
    commission.save(update_fields=["status", "paid_on", "paid_by", "bank_account", "reference", "expense", "updated_at"])
    log_event(action="commissions.paid", tenant=commission.tenant, actor=actor, object_type="commission", object_id=commission.pk, changes={"amount_idr": commission.amount_idr, "expense": str(expense.pk)})
    return commission


@transaction.atomic
def reverse_commission(*, commission_id, actor, reason):
    commission = _lock(commission_id)
    if commission.status == CommissionStatus.REVERSED:
        return commission
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "Alasan pembatalan komisi wajib diisi."})
    if commission.expense_id:  # dana kembali dari agen: kas keluar komisi dibatalkan
        expense = commission.expense
        expense.voided_at, expense.void_reason, expense.voided_by = timezone.now(), f"Komisi dibatalkan: {reason}"[:240], actor
        expense.save(update_fields=["voided_at", "void_reason", "voided_by", "updated_at"])
    _reverse(commission, reason, timezone.now())
    commission.reversed_by = actor
    commission.save(update_fields=["reversed_by", "updated_at"])
    log_event(action="commissions.reversed", tenant=commission.tenant, actor=actor, object_type="commission", object_id=commission.pk, changes={"reason": reason, "amount_idr": commission.amount_idr})
    return commission
