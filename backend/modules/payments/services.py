"""Transaksi S11. Urutan lock: [wallet →] booking → payment/invoice → peserta → charge → tenant/sequence.

Verifikasi dana tidak bergantung pada keberhasilan debit SaaS. Produksi
mencoba charge S13 dalam transaksi yang sama (wallet dikunci lebih dulu);
demo dapat dikonfirmasi tanpa ledger produksi.
"""
import hashlib
import json
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from modules.agents.services import sync_commission
from modules.audit.services import log_event
from modules.billing.services import charge_verified_booking, lock_wallet, void_pending_for_booking
from modules.booking.models import Booking, BookingParticipant
from modules.notifications.services import invoice_issued, payment_verified
from modules.payments.dates import tenant_today
from modules.payments.models import (
    FinancialSequence,
    InvoiceLine,
    PaymentAllocation,
    PaymentEvent,
    PaymentOperation,
    TravelInvoice,
    TravelInvoiceRevision,
    TravelPayment,
    TravelReceipt,
)
from modules.payments.pdf import render_financial_pdf
from modules.payments.policy import eligibility_policy, payment_rules, required_dp
from modules.tenants.environment import assert_environment_writable
from modules.tenants.models import Tenant, TenantSettings
from modules.travel_finance.models import TravelBankAccount


class Conflict(APIException):
    status_code = 409
    default_code = "conflict"


def assert_booking_payable(booking):
    assert_environment_writable(booking.tenant, booking.environment)
    if booking.status in {"DRAFT", "CANCELED", "EXPIRED"}:
        raise ValidationError({"booking": "Pembayaran memerlukan booking yang sudah direservasi dan masih aktif."})


def document_number(tenant, environment, kind):
    Tenant.objects.select_for_update().get(pk=tenant.pk)
    year = tenant_today(tenant).year
    sequence, _ = FinancialSequence.objects.get_or_create(
        tenant=tenant, environment=environment, kind=kind, year=year,
    )
    sequence.last_value += 1
    sequence.save(update_fields=["last_value", "updated_at"])
    return f"{'DEMO-' if environment == 'demo' else ''}{kind}-{year}-{sequence.last_value:06d}"


def issuer_snapshot(tenant):
    settings = TenantSettings.objects.filter(tenant=tenant).first()
    branding = settings.branding_json if settings else {}
    return {"legal_name": tenant.legal_name, "address": branding.get("address") or "-", "phone": tenant.phone}


def idempotent_operation(*, request, action, booking, target, factory):
    """Dipanggil dalam transaksi setelah booking terkunci. Respons retry identik."""
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key or len(key) > 128:
        raise ValidationError({"idempotency_key": "Header Idempotency-Key wajib, maksimal 128 karakter."})
    fingerprint = hashlib.sha256(json.dumps({"target": str(target), "data": request.data}, sort_keys=True, default=str).encode()).hexdigest()
    operation, created = PaymentOperation.objects.get_or_create(
        tenant=booking.tenant, environment=booking.environment, action=action, key=key,
        defaults={"request_hash": fingerprint},
    )
    if not created:
        operation = PaymentOperation.objects.select_for_update().get(pk=operation.pk)
        if operation.request_hash != fingerprint:
            raise Conflict("Idempotency-Key sudah dipakai untuk permintaan berbeda.")
        if operation.response_json:
            return operation.response_json
    result = factory()
    operation.response_json = result
    operation.save(update_fields=["response_json", "updated_at"])
    return result


def _invoice_lines(booking, participants):
    from modules.documents.render import format_idr

    lines = []
    for participant in participants:
        price = participant.pricing_snapshot_json
        unit, discount, extra = price.get("unit_price_idr"), price.get("discount_idr", 0), price.get("extra_idr", 0)
        if any(type(value) is not int or value < 0 for value in (unit, discount, extra)) or unit - discount + extra < 0:
            raise ValidationError({"pricing": "Snapshot harga peserta tidak valid."})
        room = price.get("room_type", "")
        description = f"{participant.pilgrim.name} · {price.get('package_name', booking.departure.package.name)}"
        if room:
            description += f" · {room}"
        if discount:
            description += f" · diskon {format_idr(discount)}"
        if extra:
            description += f" · tambahan {format_idr(extra)}"
        if discount or extra:
            description += f" ({price.get('adjustment_note', '')})"
        lines.append({
            "participant_id": str(participant.pk), "pilgrim_name": participant.pilgrim.name, "description": description,
            "amount_idr": unit - discount + extra, "room_type": room, "gross_idr": unit, "discount_idr": discount, "extra_idr": extra,
        })
    return lines


def _invoice_config(tenant):
    settings = TenantSettings.objects.filter(tenant=tenant).first()
    config = settings.invoice_config_json if settings else {}
    if any(config.get(key) not in (None, 0, "", False) for key in ("tax_idr", "tax_percent", "discount_idr", "discount_percent", "pajak")):
        raise ValidationError({"invoice_config": "Pajak/diskon otomatis belum didukung; jangan menerbitkan tagihan yang mengabaikan penyesuaian tersebut."})
    return config


def _invoice_document(*, booking, participants, number, due_at, buyer_name, policy, config, version=1, revision=None):
    lines = _invoice_lines(booking, participants)
    total = sum(line["amount_idr"] for line in lines)
    line_total = booking.price_lines.aggregate(total=Sum("amount"))["total"]
    if line_total is None or line_total != total:
        raise ValidationError({"pricing": "Baris harga booking tidak cocok dengan snapshot peserta."})
    snapshot = {
        "number": number, "environment": booking.environment, "issued_at": timezone.now().isoformat(), "timezone": booking.tenant.timezone,
        "due_at": due_at.isoformat(), "issuer": issuer_snapshot(booking.tenant),
        "booking_code": booking.code, "buyer_name": buyer_name.strip() or booking.payer_name or participants[0].pilgrim.name,
        "lines": lines, "gross_idr": sum(line["gross_idr"] for line in lines), "discount_idr": sum(line["discount_idr"] for line in lines),
        "extra_idr": sum(line["extra_idr"] for line in lines), "total_idr": total, "paid_idr": 0, "outstanding_idr": total,
        "dp_policy": policy, "notes": str(config.get("notes") or ""), "version": version,
        "bank_accounts": list(TravelBankAccount.objects.filter(active=True).values("bank_name", "account_name", "account_masked")),
    }
    if revision:
        snapshot["revision"] = revision
    pdf = render_financial_pdf(snapshot)
    return snapshot, pdf, lines, total


def _create_invoice_lines(invoice, participants, lines):
    for participant, line in zip(participants, lines, strict=True):
        InvoiceLine.objects.create(
            tenant=invoice.tenant, environment=invoice.environment, invoice=invoice,
            participant=participant, description=line["description"], amount_idr=line["amount_idr"],
        )


def _locked_participants(booking):
    participants = list(booking.participants.select_for_update().select_related("pilgrim").order_by("id"))
    if not participants:
        raise ValidationError({"participants": "Booking tidak memiliki peserta."})
    participants.sort(key=lambda row: (row.created_at, str(row.pk)))
    return participants


@transaction.atomic
def issue_invoice(*, booking_id, actor, due_at=None, buyer_name=""):
    booking = Booking.objects.select_for_update().select_related("tenant", "departure__package").get(pk=booking_id)
    assert_booking_payable(booking)
    existing = TravelInvoice.objects.filter(booking=booking).first()
    if existing:
        if due_at is not None and due_at != existing.due_at:
            raise Conflict("Invoice sudah terbit dengan tanggal jatuh tempo berbeda.")
        if buyer_name.strip() and buyer_name.strip() != existing.snapshot_json["buyer_name"]:
            raise Conflict("Invoice sudah terbit dengan nama pelanggan berbeda.")
        return existing
    policy = eligibility_policy(booking.tenant)
    participants = _locked_participants(booking)
    config = _invoice_config(booking.tenant)
    today = tenant_today(booking.tenant)
    if due_at is None:
        due_days = config.get("due_days", 7)
        if type(due_days) is not int or not 0 <= due_days <= 365:
            raise ValidationError({"due_days": "Jangka jatuh tempo harus 0–365 hari."})
        due_at = today + timedelta(days=due_days)
    if due_at < today:
        raise ValidationError({"due_at": "Jatuh tempo tidak boleh sebelum tanggal terbit."})
    number = document_number(booking.tenant, booking.environment, "INV")
    snapshot, pdf, lines, total = _invoice_document(booking=booking, participants=participants, number=number, due_at=due_at, buyer_name=buyer_name, policy=policy, config=config)
    invoice = TravelInvoice.objects.create(
        tenant=booking.tenant, environment=booking.environment, booking=booking,
        invoice_number=number, issue_at=timezone.now(), due_at=due_at, total_idr=total, balance_idr=total,
        status="PAID" if total == 0 else "ISSUED", snapshot_json=snapshot,
        pdf_data=pdf, checksum=hashlib.sha256(pdf).hexdigest(), issued_by=actor,
    )
    _create_invoice_lines(invoice, participants, lines)
    for participant in participants:
        if participant.participant_status == "REGISTERED":
            participant.participant_status = "AWAITING_DP"
            participant.save(update_fields=["participant_status", "updated_at"])
    invoice_issued(invoice)
    log_event(action="invoice.issued", tenant=booking.tenant, actor=actor, object_type="invoice", object_id=invoice.pk, changes={"number": number, "total_idr": total})
    return invoice


def auto_issue_invoice(booking, actor):
    """INV-01: terbitkan invoice saat booking sah (RESERVED). Kegagalan (mis.
    konfigurasi pajak belum didukung) tidak membatalkan reservasi kursi —
    dicatat di audit dan invoice tetap dapat diterbitkan manual."""
    try:
        with transaction.atomic():
            return issue_invoice(booking_id=booking.pk, actor=actor if getattr(actor, "is_authenticated", False) else None)
    except APIException as exc:
        log_event(action="invoice.auto_issue_failed", tenant=booking.tenant, actor=actor if getattr(actor, "is_authenticated", False) else None, object_type="booking", object_id=booking.pk, changes={"detail": exc.detail if isinstance(exc.detail, (dict, list)) else str(exc.detail)})
        return None


ACTIVE_PAYMENT_STATUSES = ["DRAFT", "SUBMITTED", "VERIFIED"]


@transaction.atomic
def revise_invoice(*, invoice_id, actor, reason, buyer_name=None, due_at=None, adjustments=None, can_discount=False):
    """INV-03: revisi berversi. Hanya untuk invoice tanpa pembayaran aktif
    (DRAFT/SUBMITTED/VERIFIED); versi lama (snapshot + PDF) diarsipkan utuh
    di `TravelInvoiceRevision`, nomor invoice tetap dan versi naik."""
    from modules.booking.services import _create_price_line, apply_adjustments

    initial = TravelInvoice.objects.get(pk=invoice_id)
    booking = Booking.objects.select_for_update().select_related("tenant", "departure__package").get(pk=initial.booking_id)
    invoice = TravelInvoice.objects.select_for_update().get(pk=invoice_id)
    assert_booking_payable(booking)
    if invoice.status == "VOIDED":
        raise ValidationError({"invoice": "Invoice dibatalkan tidak dapat direvisi."})
    if invoice.payments.filter(status__in=ACTIVE_PAYMENT_STATUSES).exists():
        raise ValidationError({"invoice": "Invoice sudah memiliki pembayaran tercatat/terverifikasi. Tolak atau reversal pembayaran terlebih dahulu sebelum merevisi."})
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "Alasan revisi wajib diisi."})
    if not adjustments and buyer_name is None and due_at is None:
        raise ValidationError({"detail": "Tidak ada perubahan untuk direvisi."})
    participants = _locked_participants(booking)
    if adjustments:
        apply_adjustments(rows=participants, adjustments=adjustments, can_discount=can_discount, key=lambda row: str(row.pk))
        _create_price_line(booking=booking)
    if buyer_name is not None:
        booking.payer_name = buyer_name.strip()
        booking.save(update_fields=["payer_name", "updated_at"])
    if due_at is not None and due_at < tenant_today(booking.tenant):
        raise ValidationError({"due_at": "Jatuh tempo tidak boleh sebelum hari ini."})
    TravelInvoiceRevision.objects.create(
        tenant=invoice.tenant, environment=invoice.environment, invoice=invoice, version=invoice.version,
        invoice_number=invoice.invoice_number, total_idr=invoice.total_idr, snapshot_json=invoice.snapshot_json,
        pdf_data=bytes(invoice.pdf_data), checksum=invoice.checksum, reason=reason, revised_by=actor,
    )
    version = invoice.version + 1
    snapshot, pdf, lines, total = _invoice_document(
        booking=booking, participants=participants, number=invoice.invoice_number, due_at=due_at or invoice.due_at,
        buyer_name=buyer_name if buyer_name is not None else invoice.snapshot_json["buyer_name"],
        policy=eligibility_policy(booking.tenant), config=_invoice_config(booking.tenant), version=version,
        revision={"version": version, "reason": reason, "previous_total_idr": invoice.total_idr},
    )
    InvoiceLine.objects.filter(invoice=invoice).delete()  # versi lama utuh di arsip revisi
    TravelInvoice.objects.filter(pk=invoice.pk).update(
        version=version, total_idr=total, balance_idr=total, status="PAID" if total == 0 else "ISSUED",
        due_at=due_at or invoice.due_at, snapshot_json=snapshot, pdf_data=pdf, checksum=hashlib.sha256(pdf).hexdigest(), updated_at=timezone.now(),
    )
    invoice.refresh_from_db()
    _create_invoice_lines(invoice, participants, lines)
    sync_commission(booking)
    invoice_issued(invoice)
    log_event(action="invoice.revised", tenant=booking.tenant, actor=actor, object_type="invoice", object_id=invoice.pk, changes={"number": invoice.invoice_number, "version": version, "reason": reason, "previous_total_idr": snapshot["revision"]["previous_total_idr"], "total_idr": total})
    return invoice


def validate_allocations(invoice, amount, allocations, *, pending=False, exclude_payment=None):
    if not allocations or sum(row["amount_idr"] for row in allocations) != amount:
        raise ValidationError({"allocations": "Seluruh nominal pembayaran harus dialokasikan secara eksplisit ke peserta."})
    ids = [str(row["booking_participant_id"]) for row in allocations]
    if len(ids) != len(set(ids)):
        raise ValidationError({"allocations": "Peserta tidak boleh berulang."})
    lines = {str(line.participant_id): line for line in invoice.lines.select_related("participant")}
    statuses = ["VERIFIED", "DRAFT", "SUBMITTED"] if pending else ["VERIFIED"]
    used = PaymentAllocation.objects.filter(invoice=invoice, payment__status__in=statuses)
    if exclude_payment is not None:
        used = used.exclude(payment=exclude_payment)
    totals = {str(row["participant_id"]): row["total"] for row in used.values("participant_id").annotate(total=Sum("amount_idr"))}
    for allocation in allocations:
        pid = str(allocation["booking_participant_id"])
        line = lines.get(pid)
        if line is None or line.participant.participant_status == "CANCELED":
            raise ValidationError({"allocations": "Peserta harus aktif dan berada pada invoice booking ini."})
        if allocation["amount_idr"] < 1 or totals.get(pid, 0) + allocation["amount_idr"] > line.amount_idr:
            raise ValidationError({"allocations": "Alokasi melebihi tagihan peserta; pembayaran berlebih ditolak."})


@transaction.atomic
def record_payment(*, invoice_id, actor, data):
    initial = TravelInvoice.objects.get(pk=invoice_id)
    booking = Booking.objects.select_for_update().get(pk=initial.booking_id)
    invoice = TravelInvoice.objects.select_for_update().get(pk=invoice_id)
    assert_booking_payable(booking)
    if invoice.status in {"VOIDED", "PAID"}:
        raise ValidationError({"invoice": "Invoice sudah lunas atau dibatalkan."})
    simulated = data.get("simulate", False)
    if (booking.environment == "demo") != simulated:
        raise ValidationError({"simulate": "Pembayaran demo wajib simulasi; pembayaran produksi tidak boleh simulasi."})
    if data["received_at"] > timezone.now():
        raise ValidationError({"received_at": "Tanggal penerimaan tidak boleh di masa depan."})
    account = data.get("bank_account")
    if account is not None:
        account = TravelBankAccount.objects.select_for_update().filter(pk=account.pk).first()
        if account is None or not account.active:
            raise ValidationError({"bank_account": "Rekening tidak aktif."})
    if data["method"] == "TRANSFER" and account is None:
        raise ValidationError({"bank_account": "Pilih rekening tujuan transfer."})
    allocations = data["allocations"]
    validate_allocations(invoice, data["amount_idr"], allocations, pending=True)
    try:
        with transaction.atomic():
            payment = TravelPayment.objects.create(
                tenant=booking.tenant, environment=booking.environment, booking=booking, invoice=invoice,
                amount_idr=data["amount_idr"], kind=data["kind"], method=data["method"], received_at=data["received_at"],
                bank_account=account, reference=data.get("reference", ""), evidence_ref=data.get("evidence_ref", ""),
                simulated=simulated, created_by=actor,
            )
    except IntegrityError:
        raise Conflict("Referensi pembayaran sudah pernah dicatat.") from None
    for row in allocations:
        PaymentAllocation.objects.create(
            tenant=booking.tenant, environment=booking.environment, payment=payment,
            invoice=invoice, participant_id=row["booking_participant_id"], amount_idr=row["amount_idr"],
        )
    log_event(action="payments.recorded", tenant=booking.tenant, actor=actor, object_type="payment", object_id=payment.pk, changes={"amount_idr": payment.amount_idr, "simulated": simulated})
    if data.get("submit", True):
        submit_payment(payment=payment, actor=actor)
    return payment


def submit_payment(*, payment, actor):
    if payment.status == "SUBMITTED":
        return payment
    if payment.status != "DRAFT":
        raise ValidationError({"status": "Hanya pembayaran DRAFT dapat diajukan."})
    if not (payment.evidence_ref or payment.reference).strip():
        raise ValidationError({"evidence_ref": "Bukti atau referensi penerimaan dana wajib diisi."})
    payment.status = "SUBMITTED"
    payment.save(update_fields=["status", "updated_at"])
    log_event(action="payments.submitted", tenant=payment.tenant, actor=actor, object_type="payment", object_id=payment.pk)
    return payment


def _verified_totals(invoice):
    return {row["participant_id"]: row["total"] for row in PaymentAllocation.objects.filter(invoice=invoice, payment__status="VERIFIED").values("participant_id").annotate(total=Sum("amount_idr"))}


def _refresh_invoice(invoice):
    paid = sum(_verified_totals(invoice).values())
    if paid > invoice.total_idr:
        raise ValidationError({"allocations": "Pembayaran terverifikasi melebihi nilai invoice."})
    invoice.balance_idr = invoice.total_idr - paid
    invoice.status = "PAID" if invoice.balance_idr == 0 else "PARTIALLY_PAID" if paid else "ISSUED"
    invoice.save(update_fields=["balance_idr", "status", "updated_at"])


def _refresh_eligibility(invoice, *, reversal=False):
    totals = _verified_totals(invoice)
    threshold = required_dp(invoice.snapshot_json["dp_policy"])
    eligible = []
    for row in BookingParticipant.objects.select_for_update().filter(booking=invoice.booking).order_by("id"):
        if row.participant_status == "CANCELED":
            continue
        qualifies = totals.get(row.pk, 0) >= threshold
        if qualifies:
            if row.dp_eligible_at is None:
                row.dp_eligible_at = timezone.now()
            if invoice.environment == "production" and row.saas_charge_state == "not_eligible":
                row.saas_charge_state = "pending_charge"
            if row.participant_status in {"REGISTERED", "AWAITING_DP", "DP_VERIFIED_PENDING_CHARGE"}:
                if invoice.environment == "demo":
                    row.participant_status = "CONFIRMED"
                else:
                    row.participant_status = "DP_VERIFIED_PENDING_CHARGE"
            eligible.append(str(row.pk))
        elif reversal and row.dp_eligible_at is not None:
            row.dp_eligible_at = None
            if row.saas_charge_state == "pending_charge":
                row.saas_charge_state = "not_eligible"
            if row.participant_status not in {"DEPARTED", "COMPLETED"}:
                row.participant_status = "REVIEW_REQUIRED"
        row.save(update_fields=["dp_eligible_at", "participant_status", "saas_charge_state", "updated_at"])
    return eligible


def _receipt(payment, actor):
    existing = TravelReceipt.objects.filter(payment=payment).first()
    if existing:
        return existing
    invoice = payment.invoice
    lines = [{"description": f"{a.participant.pilgrim.name} · {payment.kind}", "amount_idr": a.amount_idr} for a in payment.allocations.select_related("participant__pilgrim").order_by("participant_id")]
    snapshot = {
        "number": document_number(payment.tenant, payment.environment, "KWT"),
        "environment": payment.environment, "issued_at": payment.verified_at.isoformat(),
        "received_at": payment.received_at.isoformat(), "timezone": payment.tenant.timezone,
        "issuer": invoice.snapshot_json["issuer"], "booking_code": payment.booking.code,
        "buyer_name": invoice.snapshot_json["buyer_name"], "invoice_number": invoice.invoice_number,
        "kind": payment.kind, "method": payment.method, "amount_idr": payment.amount_idr,
        "lines": lines, "verified_by": actor.full_name or actor.email,
    }
    pdf = render_financial_pdf(snapshot, receipt=True)
    return TravelReceipt.objects.create(
        tenant=payment.tenant, environment=payment.environment, payment=payment,
        receipt_no=snapshot["number"], issued_at=payment.verified_at, snapshot_json=snapshot,
        pdf_data=pdf, checksum=hashlib.sha256(pdf).hexdigest(),
    )


@transaction.atomic
def verify_payment(*, payment_id, actor, note=""):
    initial = TravelPayment.objects.get(pk=payment_id)
    if initial.environment == "production":
        lock_wallet(initial.tenant)  # wallet sebelum booking: sejalan dengan retry top-up
    booking = Booking.objects.select_for_update().get(pk=initial.booking_id)
    payment = TravelPayment.objects.select_for_update().get(pk=payment_id)
    assert_booking_payable(booking)
    if payment.status == "VERIFIED":
        return payment
    if payment.status != "SUBMITTED":
        raise ValidationError({"status": "Hanya pembayaran SUBMITTED dapat diverifikasi."})
    if payment_rules(booking.tenant).get("maker_checker", False) and payment.created_by_id == actor.pk:
        raise PermissionDenied("Maker-checker aktif: pencatat tidak boleh memverifikasi pembayarannya sendiri.")
    invoice = TravelInvoice.objects.select_for_update().get(pk=payment.invoice_id)
    if invoice.status == "VOIDED":
        raise ValidationError({"invoice": "Invoice dibatalkan."})
    policy = invoice.snapshot_json.get("dp_policy")
    if not policy:
        raise ValidationError({"dp_policy": "Invoice belum memiliki snapshot kebijakan DP."})
    allocations = [{"booking_participant_id": a.participant_id, "amount_idr": a.amount_idr} for a in payment.allocations.all()]
    validate_allocations(invoice, payment.amount_idr, allocations, exclude_payment=payment)
    payment.status = "VERIFIED"
    payment.verified_at = timezone.now()
    payment.verified_by = actor
    payment.verification_note = note.strip()
    payment.eligibility_policy_json = policy
    payment.save(update_fields=["status", "verified_at", "verified_by", "verification_note", "eligibility_policy_json", "updated_at"])
    _refresh_invoice(invoice)
    eligible = _refresh_eligibility(invoice)
    sync_commission(booking)
    if payment.environment == "production":
        charge_verified_booking(booking=booking, payment=payment, actor=actor)
    receipt = _receipt(payment, actor)
    payment_verified(payment, receipt)
    PaymentEvent.objects.get_or_create(
        tenant=payment.tenant, environment=payment.environment, payment=payment, kind="payment.verified",
        defaults={"payload_json": {"payment_id": str(payment.pk), "eligible_participant_ids": eligible, "simulated": payment.simulated}},
    )
    log_event(action="payment.verified", tenant=payment.tenant, actor=actor, object_type="payment", object_id=payment.pk, changes={"amount_idr": payment.amount_idr, "eligible_participants": eligible, "simulated": payment.simulated})
    return payment


@transaction.atomic
def reject_payment(*, payment_id, actor, reason):
    initial = TravelPayment.objects.get(pk=payment_id)
    booking = Booking.objects.select_for_update().get(pk=initial.booking_id)
    payment = TravelPayment.objects.select_for_update().get(pk=payment_id)
    assert_environment_writable(booking.tenant, booking.environment)
    if payment.status not in {"DRAFT", "SUBMITTED"}:
        raise ValidationError({"status": "Pembayaran ini tidak dapat ditolak."})
    if not reason.strip():
        raise ValidationError({"reason": "Alasan penolakan wajib diisi."})
    payment.status, payment.reason = "REJECTED", reason.strip()
    payment.save(update_fields=["status", "reason", "updated_at"])
    log_event(action="payment.rejected", tenant=payment.tenant, actor=actor, object_type="payment", object_id=payment.pk, changes={"reason": reason})
    return payment


@transaction.atomic
def reverse_payment(*, payment_id, actor, reason):
    initial = TravelPayment.objects.get(pk=payment_id)
    booking = Booking.objects.select_for_update().get(pk=initial.booking_id)
    payment = TravelPayment.objects.select_for_update().get(pk=payment_id)
    assert_environment_writable(booking.tenant, booking.environment)
    if payment.status == "REVERSED":
        return payment
    if payment.status != "VERIFIED":
        raise ValidationError({"status": "Hanya pembayaran VERIFIED dapat direversal."})
    if not reason.strip():
        raise ValidationError({"reason": "Alasan reversal wajib diisi."})
    if payment.verified_by_id == actor.pk:
        raise PermissionDenied("Reversal harus disetujui petugas lain dari verifikator pembayaran.")
    payment.status, payment.reason = "REVERSED", reason.strip()
    payment.save(update_fields=["status", "reason", "updated_at"])
    invoice = TravelInvoice.objects.select_for_update().get(pk=payment.invoice_id)
    _refresh_invoice(invoice)
    _refresh_eligibility(invoice, reversal=True)
    sync_commission(booking)
    if payment.environment == "production":
        void_pending_for_booking(booking, f"DP direversal: {reason.strip()}")
    if booking.status in {"CANCELED", "EXPIRED"}:
        cancel_booking_invoice(booking, booking.cancel_reason or "Booking tidak aktif")
    receipt = TravelReceipt.objects.get(payment=payment)
    receipt.status = "REVERSED"
    receipt.save(update_fields=["status", "updated_at"])
    PaymentEvent.objects.get_or_create(tenant=payment.tenant, environment=payment.environment, payment=payment, kind="payment.reversed", defaults={"payload_json": {"reason": reason, "payment_id": str(payment.pk)}})
    log_event(action="payment.reversed", tenant=payment.tenant, actor=actor, object_type="payment", object_id=payment.pk, changes={"reason": reason, "amount_idr": payment.amount_idr})
    return payment


def cancel_booking_invoice(booking, reason):
    invoice = TravelInvoice.objects.select_for_update().filter(booking=booking).first()
    if invoice is None:
        return
    if invoice.payments.filter(status="VERIFIED").exists():
        return  # refund dana jamaah terpisah dari refund SaaS (S13); histori tidak dihapus.
    invoice.status, invoice.void_reason = "VOIDED", reason
    invoice.save(update_fields=["status", "void_reason", "updated_at"])


def booking_dp_confirmed(booking):
    rows = list(booking.participants.all())
    if not rows:
        return False, "Booking tidak memiliki peserta."
    for row in rows:
        if row.dp_eligible_at is None or row.participant_status not in {"CONFIRMED", "READY", "DEPARTED", "COMPLETED"}:
            return False, "DP setiap peserta harus memenuhi syarat dan konfirmasi SaaS harus selesai."
        if booking.environment == "production" and row.saas_charge_state not in {"charged", "waived"}:
            return False, "DP terverifikasi; konfirmasi menunggu penyelesaian charge SaaS."
    return True, ""
