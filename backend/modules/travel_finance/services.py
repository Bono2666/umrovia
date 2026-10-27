"""Kas & bank travel (MOD-11): saldo awal berotorisasi, transfer antarrekening,
maker-checker pengeluaran dan buku kas per rekening.

Kunci rekening: UUID rekening, `CASH` (tunai tanpa rekening) atau
`UNASSIGNED` (transfer lama tanpa rekening tercatat). Saldo awal berlaku
mulai tanggal `as_of`; transaksi sebelum tanggal itu dianggap sudah tercakup.
"""
from collections import defaultdict
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from modules.audit.services import log_event
from modules.payments.dates import tenant_today
from modules.payments.models import PaymentEvent, TravelPayment
from modules.tenants.models import TenantSettings
from modules.travel_finance.models import CashTransfer, OpeningBalance, TravelBankAccount, TravelExpense

CASH = "CASH"
UNASSIGNED = "UNASSIGNED"
SIGN = {"inflow_idr": 1, "transfer_in_idr": 1, "reversal_idr": -1, "expense_idr": -1, "transfer_out_idr": -1}
BUCKETS = ("opening_idr", "inflow_idr", "reversal_idr", "expense_idr", "transfer_in_idr", "transfer_out_idr")


# ------------------------------------------------------------ pengaturan --
def cash_rules(tenant):
    settings = TenantSettings.objects.filter(tenant=tenant).first()
    raw = (settings.rules_json if settings else {}).get("cash") or {}
    return {"maker_checker": bool(raw.get("maker_checker", False))} if isinstance(raw, dict) else {"maker_checker": False}


def set_cash_rules(tenant, *, maker_checker):
    settings, _ = TenantSettings.objects.get_or_create(tenant=tenant)
    rules = dict(settings.rules_json or {})
    rules["cash"] = {"maker_checker": bool(maker_checker)}
    settings.rules_json = rules
    settings.save(update_fields=["rules_json"])
    return rules["cash"]


def account_key(account_id, method=None):
    if account_id:
        return str(account_id)
    return CASH if method in (None, "CASH") else UNASSIGNED


def account_labels():
    labels = {str(a.pk): f"{a.bank_name} {a.account_masked}" for a in TravelBankAccount.objects.all()}
    labels.update({CASH: "Tunai", UNASSIGNED: "Transfer (rekening tidak dicatat)"})
    return labels


def _active_account(account_id, field):
    if not account_id:
        return None
    account = TravelBankAccount.objects.filter(pk=account_id).first()
    if account is None or not account.active:
        raise ValidationError({field: "Rekening tidak ditemukan atau nonaktif."})
    return account


# ------------------------------------------------------------- buku kas --
def ledger(tenant, environment, start_date, end_date, *, branch=None):
    """Saldo awal + mutasi per rekening untuk periode [start_date, end_date] (tanggal lokal travel).

    Hanya pembayaran terverifikasi, reversal, pengeluaran disetujui yang tidak
    dibatalkan dan transfer yang tidak dibatalkan. `branch` menyaring transaksi
    bercabang (pembayaran lewat cabang booking); saldo awal tidak bercabang.
    """
    zone = ZoneInfo(tenant.timezone or "Asia/Jakarta")
    rows = defaultdict(lambda: dict.fromkeys(BUCKETS, 0))
    anchors = {}
    if branch is None:
        for ob in OpeningBalance.objects.filter(environment=environment, status="APPROVED"):
            anchors[account_key(ob.bank_account_id)] = ob

    def post(key, day, bucket, amount):
        anchor = anchors.get(key)
        if (anchor is not None and anchor.as_of <= end_date and day < anchor.as_of) or day > end_date:
            return  # tercakup saldo awal / setelah periode
        if day < start_date:
            rows[key]["opening_idr"] += SIGN[bucket] * amount
        else:
            rows[key][bucket] += amount

    for key, anchor in anchors.items():
        if anchor.as_of <= end_date:
            rows[key]["opening_idr"] += anchor.amount_idr
    payments = TravelPayment.objects.filter(environment=environment, status__in=["VERIFIED", "REVERSED"], verified_at__isnull=False)
    reversals = PaymentEvent.objects.filter(environment=environment, kind="payment.reversed").select_related("payment")
    expenses = TravelExpense.objects.filter(environment=environment, voided_at__isnull=True, approval_status="APPROVED")
    transfers = CashTransfer.objects.filter(environment=environment, voided_at__isnull=True)
    if branch is not None:
        payments = payments.filter(booking__branch=branch)
        reversals = reversals.filter(payment__booking__branch=branch)
        expenses, transfers = expenses.filter(branch=branch), transfers.filter(branch=branch)
    for p in payments.only("amount_idr", "bank_account_id", "method", "verified_at"):
        post(account_key(p.bank_account_id, p.method), p.verified_at.astimezone(zone).date(), "inflow_idr", p.amount_idr)
    for event in reversals:
        p = event.payment
        post(account_key(p.bank_account_id, p.method), event.created_at.astimezone(zone).date(), "reversal_idr", p.amount_idr)
    for e in expenses.only("amount_idr", "bank_account_id", "spent_on"):
        post(account_key(e.bank_account_id), e.spent_on, "expense_idr", e.amount_idr)
    for t in transfers.only("amount_idr", "from_account_id", "to_account_id", "transferred_on"):
        post(account_key(t.from_account_id), t.transferred_on, "transfer_out_idr", t.amount_idr)
        post(account_key(t.to_account_id), t.transferred_on, "transfer_in_idr", t.amount_idr)
    labels = account_labels()
    result = []
    for key, values in sorted(rows.items(), key=lambda item: labels.get(item[0], item[0])):
        closing = values["opening_idr"] + values["inflow_idr"] - values["reversal_idr"] - values["expense_idr"] + values["transfer_in_idr"] - values["transfer_out_idr"]
        anchor = anchors.get(key)
        result.append({"key": key, "account": labels.get(key, "Rekening lain"), **values, "closing_idr": closing,
                       "opening_as_of": anchor.as_of.isoformat() if anchor else None})
    return result


# ------------------------------------------------------------ saldo awal --
@transaction.atomic
def request_opening_balance(*, tenant, environment, bank_account_id, as_of, amount_idr, reason, actor):
    account = _active_account(bank_account_id, "bank_account")
    if as_of > tenant_today(tenant):
        raise ValidationError({"as_of": "Tanggal saldo awal tidak boleh di masa depan."})
    current = OpeningBalance.objects.select_for_update().filter(environment=environment, bank_account=account, status="APPROVED").first()
    pending = OpeningBalance.objects.filter(environment=environment, bank_account=account, status="PENDING").exists()
    if current is not None and not (reason or "").strip():
        raise ValidationError({"reason": "Koreksi saldo awal wajib disertai alasan."})
    if pending:
        raise ValidationError({"bank_account": "Masih ada koreksi saldo awal yang menunggu persetujuan untuk rekening ini."})
    row = OpeningBalance.objects.create(
        tenant=tenant, environment=environment, bank_account=account, as_of=as_of, amount_idr=amount_idr,
        reason=(reason or "").strip()[:240], created_by=actor, status="PENDING" if current else "APPROVED",
        decided_by=None if current else actor, decided_at=None if current else timezone.now(),
    )
    log_event(action="cash.opening_balance_requested" if current else "cash.opening_balance_set", tenant=tenant, actor=actor, object_type="opening_balance", object_id=row.pk,
              changes={"account": account_key(row.bank_account_id), "as_of": as_of.isoformat(), "amount_idr": amount_idr, "reason": row.reason})
    return row


@transaction.atomic
def decide_opening_balance(*, tenant, balance_id, actor, approve, note=""):
    row = OpeningBalance.objects.select_for_update().get(pk=balance_id)
    if row.status != "PENDING":
        raise ValidationError({"status": "Koreksi ini sudah diputuskan."})
    if row.created_by_id == actor.pk and cash_rules(tenant)["maker_checker"]:
        raise PermissionDenied("Maker-checker kas aktif: koreksi saldo awal harus disetujui staf lain.")
    if not approve and not (note or "").strip():
        raise ValidationError({"note": "Alasan penolakan wajib diisi."})
    if approve:
        OpeningBalance.objects.filter(environment=row.environment, bank_account_id=row.bank_account_id, status="APPROVED").update(status="SUPERSEDED", updated_at=timezone.now())
    row.status, row.decided_by, row.decided_at, row.decision_note = ("APPROVED" if approve else "REJECTED"), actor, timezone.now(), (note or "").strip()[:240]
    row.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    log_event(action=f"cash.opening_balance_{'approved' if approve else 'rejected'}", tenant=tenant, actor=actor, object_type="opening_balance", object_id=row.pk, changes={"amount_idr": row.amount_idr, "note": row.decision_note})
    return row


# -------------------------------------------------------------- transfer --
@transaction.atomic
def record_transfer(*, tenant, environment, data, actor, branch=None):
    source = _active_account(data.get("from_account"), "from_account")
    target = _active_account(data.get("to_account"), "to_account")
    if (source.pk if source else None) == (target.pk if target else None):
        raise ValidationError({"to_account": "Rekening asal dan tujuan harus berbeda."})
    if data["transferred_on"] > tenant_today(tenant):
        raise ValidationError({"transferred_on": "Tanggal transfer tidak boleh di masa depan."})
    transfer = CashTransfer.objects.create(
        tenant=tenant, environment=environment, transferred_on=data["transferred_on"], from_account=source, to_account=target,
        amount_idr=data["amount_idr"], description=data.get("description", "").strip(), reference=data.get("reference", "").strip(),
        branch=branch, created_by=actor,
    )
    log_event(action="cash.transfer_recorded", tenant=tenant, actor=actor, object_type="cash_transfer", object_id=transfer.pk,
              changes={"from": account_key(transfer.from_account_id), "to": account_key(transfer.to_account_id), "amount_idr": transfer.amount_idr})
    return transfer


@transaction.atomic
def void_transfer(*, transfer_id, actor, reason):
    transfer = CashTransfer.objects.select_for_update().get(pk=transfer_id)
    if transfer.voided_at is None:
        transfer.voided_at, transfer.void_reason, transfer.voided_by = timezone.now(), reason.strip()[:240], actor
        transfer.save(update_fields=["voided_at", "void_reason", "voided_by", "updated_at"])
        log_event(action="cash.transfer_voided", tenant=transfer.tenant, actor=actor, object_type="cash_transfer", object_id=transfer.pk, changes={"reason": transfer.void_reason})
    return transfer


# ---------------------------------------------------- persetujuan biaya --
@transaction.atomic
def decide_expense(*, expense_id, actor, approve, reason=""):
    expense = TravelExpense.objects.select_for_update(of=("self",)).get(pk=expense_id)
    if expense.approval_status != "PENDING":
        raise ValidationError({"status": "Pengeluaran ini tidak menunggu persetujuan."})
    if expense.voided_at is not None:
        raise ValidationError({"status": "Pengeluaran sudah dibatalkan."})
    if expense.created_by_id == actor.pk:
        raise PermissionDenied("Pengeluaran harus disetujui staf selain pencatatnya (maker-checker).")
    if not approve and not (reason or "").strip():
        raise ValidationError({"reason": "Alasan penolakan wajib diisi."})
    expense.approval_status = "APPROVED" if approve else "REJECTED"
    expense.approved_by, expense.approved_at, expense.rejection_reason = actor, timezone.now(), (reason or "").strip()[:240]
    expense.save(update_fields=["approval_status", "approved_by", "approved_at", "rejection_reason", "updated_at"])
    log_event(action=f"expenses.{'approved' if approve else 'rejected'}", tenant=expense.tenant, actor=actor, object_type="travel_expense", object_id=expense.pk, changes={"amount_idr": expense.amount_idr, "reason": expense.rejection_reason})
    return expense
