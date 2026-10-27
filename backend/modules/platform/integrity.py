"""Pemeriksaan integritas read-only (S19; Spec §11.2 `backup_validation`, `reconciliation_daily`).

Dipakai untuk drill restore (bandingkan sumber vs hasil restore), job harian
worker dan gate rilis. Tidak pernah menulis/memperbaiki data: hanya melapor.
Data jamaah tidak dibaca selain hitungan baris.
"""
import hashlib
from collections import Counter

from django.apps import apps
from django.db import connection
from django.db.models import Count, Sum

from modules.billing.models import SaaSCharge
from modules.booking.models import BookingParticipant
from modules.departures.models import Departure
from modules.notifications.models import Notification, NotificationJob
from modules.payments.models import InvoiceLine, PaymentAllocation, TravelInvoice, TravelReceipt
from modules.tenants.managers import TenantScopedModel
from modules.tenants.models import Tenant
from modules.wallet.models import Wallet, WalletLedger
from modules.wallet.services import platform_tenant_context

# Membership dibaca middleware sebelum konteks tenant ada (ADR-0003) — dilindungi lewat filter server-side.
RLS_EXEMPT = {"tenants_tenantmembership"}
HOLDING_EXCLUDED = {"DRAFT", "CANCELED", "EXPIRED"}


def _check(name, ok, detail=""):
    return {"name": name, "ok": bool(ok), "detail": detail}


def rls_check():
    tables = sorted({m._meta.db_table for m in apps.get_models() if issubclass(m, TenantScopedModel) and m._meta.managed} - RLS_EXEMPT)
    with connection.cursor() as cursor:
        cursor.execute("SELECT relname FROM pg_class WHERE relname = ANY(%s) AND relrowsecurity AND relforcerowsecurity", [tables])
        protected = {row[0] for row in cursor.fetchall()}
    missing = [t for t in tables if t not in protected]
    return _check("RLS ENABLE+FORCE pada semua tabel tenant", not missing, f"{len(protected)}/{len(tables)} tabel" + (f"; tanpa RLS: {', '.join(missing)}" if missing else ""))


def _wallet_problems():
    problems = []
    for wallet in Wallet.objects.all():
        balance, expected = 0, 1
        for entry in WalletLedger.objects.filter(wallet=wallet).order_by("sequence").only("sequence", "signed_amount_idr", "balance_after_idr"):
            balance += entry.signed_amount_idr
            if entry.sequence != expected or entry.balance_after_idr != balance:
                problems.append(f"ledger wallet {wallet.pk} putus di urutan {entry.sequence}")
                break
            expected += 1
        if wallet.balance_cached_idr != balance or balance < 0:
            problems.append(f"saldo wallet {wallet.pk}: cache {wallet.balance_cached_idr} ≠ ledger {balance}")
    for charge in SaaSCharge.objects.filter(status__in=["POSTED", "REFUNDED"]).select_related("ledger_entry"):
        if charge.ledger_entry is None or charge.ledger_entry.kind != "DEBIT" or charge.ledger_entry.signed_amount_idr != -charge.unit_price_idr:
            problems.append(f"charge {charge.pk} tanpa debit ledger yang cocok")
    duplicates = SaaSCharge.objects.exclude(status="VOID").values("participant_id").annotate(n=Count("id")).filter(n__gt=1)
    if duplicates.exists():
        problems.append(f"{duplicates.count()} peserta memiliki >1 charge aktif")
    return problems


def _invoice_problems():
    problems = []
    for invoice in TravelInvoice.objects.exclude(status="VOIDED"):
        lines = InvoiceLine.objects.filter(invoice=invoice).aggregate(t=Sum("amount_idr"))["t"] or 0
        paid = PaymentAllocation.objects.filter(invoice=invoice, payment__status="VERIFIED").aggregate(t=Sum("amount_idr"))["t"] or 0
        if lines != invoice.total_idr or invoice.balance_idr != invoice.total_idr - paid:
            problems.append(f"invoice {invoice.invoice_number}: total {invoice.total_idr}/baris {lines}, saldo {invoice.balance_idr}/seharusnya {invoice.total_idr - paid}")
    return problems


def _document_problems():
    problems = []
    for model in (TravelInvoice, TravelReceipt):
        for doc in model.objects.only("pk", "pdf_data", "checksum"):
            if hashlib.sha256(bytes(doc.pdf_data)).hexdigest() != doc.checksum:
                problems.append(f"{model._meta.model_name} {doc.pk}: checksum PDF tidak cocok")
    return problems


def _seat_problems():
    problems = []
    holding = Counter(BookingParticipant.objects.exclude(booking__status__in=HOLDING_EXCLUDED).values_list("booking__departure_id", flat=True))
    for dep in Departure.objects.only("pk", "code", "seats_taken", "seats_blocked", "seat_capacity"):
        if dep.seats_taken != holding.get(dep.pk, 0) or dep.seats_taken + dep.seats_blocked > dep.seat_capacity:
            problems.append(f"keberangkatan {dep.code}: kursi {dep.seats_taken}, peserta aktif {holding.get(dep.pk, 0)}, kapasitas {dep.seat_capacity}")
    return problems


def _notification_problems(tenant):
    jobs = set(NotificationJob.objects.filter(tenant=tenant).values_list("id", flat=True))
    open_rows = set(Notification.objects.filter(channel="EMAIL", status__in=["PENDING", "FAILED"]).values_list("id", flat=True))
    problems = []
    if jobs - open_rows:
        problems.append(f"{len(jobs - open_rows)} job antrean tanpa notifikasi terbuka")
    if open_rows - jobs:
        problems.append(f"{len(open_rows - jobs)} email terbuka tanpa job antrean")
    return problems


def _counts(tenant) -> Counter:
    counts = Counter()
    for model in apps.get_models():
        if issubclass(model, TenantScopedModel) and model._meta.managed and model._meta.db_table not in RLS_EXEMPT:
            counts[model._meta.db_table] += model.objects.count()
    return counts


def run() -> dict:
    checks = [rls_check()]
    totals = Counter()
    per_check = {"wallet": [], "invoice": [], "documents": [], "seats": [], "notifications": []}
    for tenant in Tenant.objects.order_by("created_at"):
        with platform_tenant_context(tenant.pk) as scoped:
            per_check["wallet"] += _wallet_problems()
            per_check["invoice"] += _invoice_problems()
            per_check["documents"] += _document_problems()
            per_check["seats"] += _seat_problems()
            per_check["notifications"] += _notification_problems(scoped)
            totals += _counts(scoped)
    labels = {
        "wallet": "Ledger SaaS Wallet berantai & saldo = ledger; charge ↔ debit",
        "invoice": "Invoice: total = baris, saldo = total − pembayaran terverifikasi",
        "documents": "PDF invoice/kuitansi cocok dengan checksum",
        "seats": "Kursi terisi = peserta booking aktif, tidak melebihi kapasitas",
        "notifications": "Antrean email konsisten dengan notifikasi terbuka",
    }
    for key, problems in per_check.items():
        checks.append(_check(labels[key], not problems, "; ".join(problems[:5]) + (f" (+{len(problems) - 5} lagi)" if len(problems) > 5 else "")))
    from django.contrib.auth import get_user_model

    totals["tenants_tenant"] = Tenant.objects.count()
    totals["identity_user"] = get_user_model().objects.count()
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM audit_auditevent")
        totals["audit_auditevent"] = cursor.fetchone()[0]
    return {"ok": all(c["ok"] for c in checks), "checks": checks, "counts": dict(sorted(totals.items()))}
