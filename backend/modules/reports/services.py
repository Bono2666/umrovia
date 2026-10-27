"""Laporan siap pakai (S17, PRD §51.5 RPT-01…06, Spec §12).

Setiap laporan dihitung langsung dari catatan transaksi sumber pada saat
diminta (`as_of`) — tidak ada tabel agregat yang bisa basi. Struktur payload
sama untuk layar dan ekspor: `kpis`, `sections` (kolom bertipe + baris +
total) dan `checks` (rekonsiliasi terhadap catatan sumber, RPT-04).

Pengakuan: pembayaran diakui pada `verified_at`, reversal pada waktu event
`payment.reversed`, pengeluaran pada `spent_on`; pengeluaran yang dibatalkan
tidak dihitung. Keuangan travel (DP, kas/bank) dipisahkan tegas dari SaaS
Wallet (dana prabayar untuk biaya layanan Umrovia).
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from django.db.models import Count, Max, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from modules.billing.models import SaaSAdjustment, SaaSCharge
from modules.booking.models import Booking, BookingParticipant
from modules.departures.models import Departure, DepartureStatus
from modules.documents.render import format_idr
from modules.manifest.models import ManifestVersion
from modules.manifest.services import readiness
from modules.payments.models import InvoiceLine, PaymentAllocation, PaymentEvent, TravelInvoice, TravelPayment
from modules.travel_finance.models import ExpenseCategory, TravelBankAccount, TravelExpense
from modules.wallet.models import Wallet, WalletLedger, WalletTopup

MAX_RANGE_DAYS = 731
ROW_LIMIT = 500
INACTIVE_BOOKINGS = {"DRAFT", "CANCELED", "EXPIRED"}
OPEN_INVOICES = {"ISSUED", "PARTIALLY_PAID"}
AGING = [("current", "Belum jatuh tempo", None, 0), ("d30", "1–30 hari", 1, 30), ("d60", "31–60 hari", 31, 60), ("d90", "61–90 hari", 61, 90), ("d90plus", "> 90 hari", 91, None)]
PAYMENT_KIND = {"DP": "DP", "INSTALLMENT": "Cicilan", "BALANCE": "Pelunasan"}


# ----------------------------------------------------------------- filters --


def _date(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValidationError({field: "Format tanggal YYYY-MM-DD."}) from None


def _uuid(value, field):
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        raise ValidationError({field: "ID tidak valid."}) from None


def parse_filters(params, tenant):
    """Rentang tanggal lokal tenant (inklusif) + filter paket/keberangkatan/status."""
    zone = ZoneInfo(tenant.timezone or "Asia/Jakarta")
    today = timezone.now().astimezone(zone).date()
    start = _date(params["from"], "from") if params.get("from") else today.replace(day=1)
    end = _date(params["to"], "to") if params.get("to") else today
    if start > end:
        raise ValidationError({"to": "Tanggal akhir tidak boleh sebelum tanggal awal."})
    if (end - start).days > MAX_RANGE_DAYS:
        raise ValidationError({"from": "Rentang laporan maksimal 2 tahun."})
    status = params.get("status") or ""
    if status and status not in DepartureStatus.values:
        raise ValidationError({"status": "Status keberangkatan tidak dikenal."})
    return {
        "from": start, "to": end, "zone": zone, "today": today,
        "start_dt": datetime.combine(start, time.min, zone), "end_dt": datetime.combine(end + timedelta(days=1), time.min, zone),
        "package": _uuid(params.get("package"), "package"), "departure": _uuid(params.get("departure"), "departure"), "status": status,
    }


def _envelope(kind, title, tenant, environment, f, **extra):
    return {
        "report": kind, "title": title, "travel": tenant.display_name, "environment": environment,
        "as_of": timezone.now().isoformat(), "timezone": str(f["zone"]),
        "period": {"from": f["from"].isoformat(), "to": f["to"].isoformat()},
        "filters": {key: str(f[key]) if f[key] else "" for key in ("package", "departure", "status")},
        **extra,
    }


def _col(key, label, kind="text"):
    return {"key": key, "label": label, "type": kind}


def _section(key, title, columns, rows, *, totals=None, description="", truncated=False):
    return {"key": key, "title": title, "description": description, "columns": columns, "rows": rows, "totals": totals, "truncated": truncated}


def _sum(rows, *keys):
    return {key: sum(row.get(key) or 0 for row in rows) for key in keys}


def _rp(value):
    value = int(value or 0)
    return ("−" if value < 0 else "") + format_idr(abs(value))


def _pct(part, whole):
    return round(part * 100 / whole, 1) if whole else None


def _local_date(value, zone):
    return value.astimezone(zone).date().isoformat() if value else None


def _scope_departures(qs, f, prefix=""):
    """Filter keberangkatan/paket; `prefix` = jalur ke Departure ("" bila qs adalah Departure)."""
    if f["departure"]:
        qs = qs.filter(**{f"{prefix}id" if prefix else "pk": f["departure"]})
    if f["package"]:
        qs = qs.filter(**{f"{prefix}package_id": f["package"]})
    return qs


# ------------------------------------------------------------- operational --


def operational(tenant, environment, f):
    """RPT-01: okupansi, booking, DP, konfirmasi, dokumen dan kesiapan per keberangkatan."""
    deps = Departure.objects.filter(environment=environment, start_at__gte=f["start_dt"], start_at__lt=f["end_dt"]).select_related("package")
    deps = _scope_departures(deps, f)
    if f["status"]:
        deps = deps.filter(status=f["status"])
    deps = list(deps.order_by("start_at", "code")[: ROW_LIMIT + 1])
    truncated = len(deps) > ROW_LIMIT
    deps = deps[:ROW_LIMIT]
    ids = [d.pk for d in deps]
    bookings = dict(Booking.objects.filter(departure_id__in=ids).exclude(status__in=INACTIVE_BOOKINGS).values_list("departure_id").annotate(n=Count("id")))
    departed = dict(
        BookingParticipant.objects.filter(booking__departure_id__in=ids, participant_status__in=["DEPARTED", "COMPLETED"])
        .values_list("booking__departure_id").annotate(n=Count("id"))
    )
    holding = dict(
        BookingParticipant.objects.filter(booking__departure_id__in=ids).exclude(booking__status__in=INACTIVE_BOOKINGS)
        .values_list("booking__departure_id").annotate(n=Count("id"))
    )
    versions = {row["departure_id"]: row["latest"] for row in ManifestVersion.objects.filter(departure_id__in=ids).values("departure_id").annotate(latest=Max("version_no"))}
    status_label = dict(DepartureStatus.choices)
    rows = []
    for dep in deps:
        ready = readiness(dep)
        rows.append({
            "departure_id": str(dep.pk), "code": dep.code, "package": dep.package.name, "package_id": str(dep.package_id),
            "start_at": _local_date(dep.start_at, f["zone"]), "status": status_label.get(dep.status, dep.status),
            "capacity": dep.seat_capacity, "seats_taken": dep.seats_taken, "available": dep.available_seats,
            "occupancy": _pct(dep.seats_taken, dep.seat_capacity), "bookings": bookings.get(dep.pk, 0),
            "participants": ready["participants"], "dp_received": ready["dp_received"], "confirmed": ready["confirmed"],
            "departed": departed.get(dep.pk, 0), "docs_complete": ready["docs_complete"],
            "readiness": "Lengkap" if ready["checklist_ready"] else f"Kurang {ready['gap_count']}",
            "gap_count": ready["gap_count"], "manifest": f"v{versions[dep.pk]}" if dep.pk in versions else "Belum",
        })
    counts = ("capacity", "seats_taken", "available", "bookings", "participants", "dp_received", "confirmed", "departed", "docs_complete", "gap_count")
    totals = _sum(rows, *counts)
    totals["occupancy"] = _pct(totals["seats_taken"], totals["capacity"])
    by_package = {}
    for row in rows:
        item = by_package.setdefault(row["package_id"], {"package": row["package"], "departures": 0, **{key: 0 for key in ("capacity", "seats_taken", "bookings", "participants", "dp_received", "confirmed", "departed")}})
        item["departures"] += 1
        for key in ("capacity", "seats_taken", "bookings", "participants", "dp_received", "confirmed", "departed"):
            item[key] += row[key]
    packages = sorted(by_package.values(), key=lambda item: item["package"])
    for item in packages:
        item["occupancy"] = _pct(item["seats_taken"], item["capacity"])
    new_bookings = Booking.objects.filter(environment=environment, booked_at__gte=f["start_dt"], booked_at__lt=f["end_dt"]).exclude(status__in={"DRAFT"})
    new_bookings = _scope_departures(new_bookings, f, "departure__")
    count_cols = [_col("capacity", "Kapasitas", "int"), _col("seats_taken", "Kursi terisi", "int"), _col("occupancy", "Okupansi", "percent")]
    return _envelope(
        "operational", "Laporan operasional", tenant, environment, f,
        kpis=[
            {"key": "departures", "label": "Keberangkatan", "value": len(rows), "type": "int", "hint": "Berangkat dalam periode"},
            {"key": "participants", "label": "Jamaah aktif", "value": totals["participants"], "type": "int", "hint": f"{new_bookings.count()} booking baru dalam periode"},
            {"key": "dp_received", "label": "DP diterima", "value": totals["dp_received"], "type": "int", "hint": f"{totals['confirmed']} terkonfirmasi"},
            {"key": "occupancy", "label": "Okupansi kursi", "value": totals["occupancy"], "type": "percent", "hint": f"{totals['seats_taken']} dari {totals['capacity']} kursi"},
            {"key": "docs_complete", "label": "Dokumen lengkap", "value": totals["docs_complete"], "type": "int", "hint": f"{sum(1 for r in rows if r['gap_count'])} keberangkatan belum siap"},
        ],
        sections=[
            _section("departures", "Kesiapan per keberangkatan", [
                _col("code", "Keberangkatan"), _col("package", "Paket"), _col("start_at", "Berangkat", "date"), _col("status", "Status"),
                *count_cols, _col("bookings", "Booking", "int"), _col("participants", "Jamaah", "int"), _col("dp_received", "DP diterima", "int"),
                _col("confirmed", "Terkonfirmasi", "int"), _col("docs_complete", "Dokumen lengkap", "int"), _col("readiness", "Checklist"), _col("manifest", "Manifest"),
            ], rows, totals={**totals, "code": "Total"}, truncated=truncated),
            _section("packages", "Jamaah per paket", [
                _col("package", "Paket"), _col("departures", "Keberangkatan", "int"), *count_cols, _col("bookings", "Booking", "int"),
                _col("participants", "Jamaah", "int"), _col("dp_received", "DP diterima", "int"), _col("confirmed", "Terkonfirmasi", "int"), _col("departed", "Berangkat", "int"),
            ], packages, totals={**_sum(packages, "departures", "capacity", "seats_taken", "bookings", "participants", "dp_received", "confirmed", "departed"), "occupancy": totals["occupancy"], "package": "Total"}),
        ],
        checks=[
            {"label": "Kursi terisi = peserta booking yang menahan kursi", "ok": all(dep.seats_taken == holding.get(dep.pk, 0) for dep in deps),
             "detail": f"{sum(d.seats_taken for d in deps)} kursi tercatat · {sum(holding.values())} peserta booking aktif"},
        ],
    )


# ----------------------------------------------------------------- finance --


def _account_key(payment_or_expense, method=None):
    if payment_or_expense.bank_account_id:
        return str(payment_or_expense.bank_account_id)
    return "CASH" if method in (None, "CASH") else "UNASSIGNED"


def finance(tenant, environment, f):
    """RPT-02/04: invoice, penerimaan, reversal, piutang & aging, kas/bank, pengeluaran, margin estimasi."""
    zone, start, end = f["zone"], f["start_dt"], f["end_dt"]
    invoices = _scope_departures(TravelInvoice.objects.filter(environment=environment), f, "booking__departure__")
    payments = _scope_departures(TravelPayment.objects.filter(environment=environment, status__in=["VERIFIED", "REVERSED"], verified_at__isnull=False), f, "booking__departure__")
    reversals = _scope_departures(PaymentEvent.objects.filter(environment=environment, kind="payment.reversed"), f, "payment__booking__departure__").select_related("payment")
    expenses = TravelExpense.objects.filter(environment=environment, voided_at__isnull=True)
    if f["departure"] or f["package"]:
        expenses = _scope_departures(expenses.filter(departure__isnull=False), f, "departure__")

    issued = invoices.filter(issue_at__gte=start, issue_at__lt=end)
    issued_active = issued.exclude(status="VOIDED").aggregate(n=Count("id"), total=Sum("total_idr"))
    issued_void = issued.filter(status="VOIDED").aggregate(n=Count("id"), total=Sum("total_idr"))
    period_payments = list(payments.filter(verified_at__gte=start, verified_at__lt=end).select_related("bank_account", "booking"))
    period_reversals = list(reversals.filter(created_at__gte=start, created_at__lt=end))
    gross = sum(p.amount_idr for p in period_payments)
    reversed_total = sum(r.payment.amount_idr for r in period_reversals)
    period_expenses = list(expenses.filter(spent_on__gte=f["from"], spent_on__lte=f["to"]).select_related("departure__package", "bank_account"))
    spent = sum(e.amount_idr for e in period_expenses)

    receipts_by_kind = defaultdict(lambda: {"count": 0, "amount_idr": 0})
    for payment in period_payments:
        row = receipts_by_kind[payment.kind]
        row["count"] += 1
        row["amount_idr"] += payment.amount_idr
    receipts_rows = [{"kind": PAYMENT_KIND.get(kind, kind), **values} for kind, values in sorted(receipts_by_kind.items())]
    if period_reversals:
        receipts_rows.append({"kind": "Reversal", "count": len(period_reversals), "amount_idr": -reversed_total})

    # Piutang per saat laporan dibuat (as_of): invoice terbuka dan umur jatuh tempo.
    open_invoices = list(invoices.filter(status__in=OPEN_INVOICES, balance_idr__gt=0).select_related("booking").order_by("due_at", "invoice_number")[: ROW_LIMIT + 1])
    truncated_ar = len(open_invoices) > ROW_LIMIT
    aging_totals = {key: 0 for key, *_ in AGING}
    ar_rows = []
    for invoice in open_invoices[:ROW_LIMIT]:
        overdue = (f["today"] - invoice.due_at).days
        bucket = next(key for key, _, low, high in AGING if (low is None and overdue <= 0) or (low is not None and overdue >= low and (high is None or overdue <= high)))
        aging_totals[bucket] += invoice.balance_idr
        ar_rows.append({
            "invoice_number": invoice.invoice_number, "booking_code": invoice.booking.code, "buyer": invoice.snapshot_json.get("buyer_name", ""),
            "due_at": invoice.due_at.isoformat(), "total_idr": invoice.total_idr, "paid_idr": invoice.total_idr - invoice.balance_idr,
            "balance_idr": invoice.balance_idr, "overdue_days": max(overdue, 0), "aging": dict((k, label) for k, label, *_ in AGING)[bucket],
        })
    outstanding = invoices.filter(status__in=OPEN_INVOICES).aggregate(total=Sum("balance_idr"))["total"] or 0

    # Kas/bank: saldo awal (sebelum periode) + masuk − reversal − pengeluaran = saldo akhir.
    accounts = {str(a.pk): f"{a.bank_name} {a.account_masked}" for a in TravelBankAccount.objects.all()}
    accounts.update({"CASH": "Tunai", "UNASSIGNED": "Transfer (rekening tidak dicatat)"})
    ledger = defaultdict(lambda: {"opening_idr": 0, "inflow_idr": 0, "reversal_idr": 0, "expense_idr": 0})
    for payment in payments.filter(verified_at__lt=end).only("amount_idr", "bank_account_id", "method", "verified_at"):
        bucket = ledger[_account_key(payment, payment.method)]
        bucket["inflow_idr" if payment.verified_at >= start else "opening_idr"] += payment.amount_idr
    for event in reversals.filter(created_at__lt=end):
        bucket = ledger[_account_key(event.payment, event.payment.method)]
        if event.created_at >= start:
            bucket["reversal_idr"] += event.payment.amount_idr
        else:
            bucket["opening_idr"] -= event.payment.amount_idr
    for expense in expenses.filter(spent_on__lte=f["to"]).only("amount_idr", "bank_account_id", "spent_on"):
        bucket = ledger[_account_key(expense)]
        if expense.spent_on >= f["from"]:
            bucket["expense_idr"] += expense.amount_idr
        else:
            bucket["opening_idr"] -= expense.amount_idr
    cash_rows = []
    for key, values in sorted(ledger.items(), key=lambda item: accounts.get(item[0], item[0])):
        closing = values["opening_idr"] + values["inflow_idr"] - values["reversal_idr"] - values["expense_idr"]
        cash_rows.append({"account": accounts.get(key, "Rekening lain"), **values, "closing_idr": closing})

    category_label = dict(ExpenseCategory.choices)
    by_category = defaultdict(lambda: {"count": 0, "amount_idr": 0})
    by_departure = defaultdict(lambda: {"count": 0, "amount_idr": 0})
    for expense in period_expenses:
        by_category[expense.category]["count"] += 1
        by_category[expense.category]["amount_idr"] += expense.amount_idr
        label = f"{expense.departure.code} · {expense.departure.package.name}" if expense.departure else "Umum / kantor"
        by_departure[label]["count"] += 1
        by_departure[label]["amount_idr"] += expense.amount_idr
    category_rows = [{"category": category_label.get(k, k), **v} for k, v in sorted(by_category.items(), key=lambda item: -item[1]["amount_idr"])]
    expense_dep_rows = [{"departure": k, **v} for k, v in sorted(by_departure.items())]

    # Margin estimasi: keberangkatan yang berangkat dalam periode ATAU punya invoice/biaya dalam periode
    # (penjualan dan biaya biasanya terjadi berbulan-bulan sebelum tanggal berangkat).
    active_ids = set(issued.values_list("booking__departure_id", flat=True)) | {e.departure_id for e in period_expenses if e.departure_id}
    deps = _scope_departures(Departure.objects.filter(environment=environment).filter(Q(start_at__gte=start, start_at__lt=end) | Q(pk__in=active_ids)), f)
    deps = deps.select_related("package").order_by("start_at")[:ROW_LIMIT]
    dep_ids = [d.pk for d in deps]
    sales = dict(InvoiceLine.objects.filter(invoice__booking__departure_id__in=dep_ids).exclude(invoice__status="VOIDED").values_list("invoice__booking__departure_id").annotate(t=Sum("amount_idr")))
    received = dict(PaymentAllocation.objects.filter(invoice__booking__departure_id__in=dep_ids, payment__status="VERIFIED").values_list("invoice__booking__departure_id").annotate(t=Sum("amount_idr")))
    costs = dict(TravelExpense.objects.filter(departure_id__in=dep_ids, voided_at__isnull=True).values_list("departure_id").annotate(t=Sum("amount_idr")))
    margin_rows = []
    for dep in deps:
        sale, cost = sales.get(dep.pk, 0), costs.get(dep.pk, 0)
        margin_rows.append({
            "departure": f"{dep.code} · {dep.package.name}", "start_at": _local_date(dep.start_at, zone), "sales_idr": sale,
            "received_idr": received.get(dep.pk, 0), "expense_idr": cost, "margin_idr": sale - cost,
            "margin_pct": _pct(sale - cost, sale), "note": "Estimasi — biaya belum dicatat" if not cost else "Estimasi",
        })

    # RPT-04: rekonsiliasi terhadap catatan sumber.
    active_invoices = invoices.exclude(status="VOIDED")
    invoice_totals = active_invoices.aggregate(total=Sum("total_idr"), balance=Sum("balance_idr"))
    allocated = PaymentAllocation.objects.filter(invoice__in=active_invoices, payment__status="VERIFIED").aggregate(t=Sum("amount_idr"))["t"] or 0
    allocated_period = PaymentAllocation.objects.filter(payment__in=[p.pk for p in period_payments]).aggregate(t=Sum("amount_idr"))["t"] or 0
    net = gross - reversed_total
    cash_net = sum(row["inflow_idr"] - row["reversal_idr"] - row["expense_idr"] for row in cash_rows)
    checks = [
        {"label": "Piutang = total invoice − pembayaran terverifikasi teralokasi", "ok": (invoice_totals["total"] or 0) - allocated == (invoice_totals["balance"] or 0),
         "detail": f"Invoice aktif {_rp(invoice_totals['total'])} − alokasi {_rp(allocated)} = saldo {_rp(invoice_totals['balance'])}"},
        {"label": "Penerimaan periode = alokasi per jamaah", "ok": gross == allocated_period, "detail": f"Penerimaan {_rp(gross)} · alokasi {_rp(allocated_period)}"},
        {"label": "Mutasi kas/bank = penerimaan bersih − pengeluaran", "ok": cash_net == net - spent, "detail": f"Mutasi {_rp(cash_net)} · bersih {_rp(net)} − pengeluaran {_rp(spent)}"},
    ]
    money = "money"
    return _envelope(
        "finance", "Laporan keuangan travel", tenant, environment, f,
        note="Dana DP dan pembayaran jamaah milik travel. Saldo SaaS Wallet dilaporkan terpisah dan tidak termasuk di sini.",
        kpis=[
            {"key": "invoiced", "label": "Invoice terbit", "value": issued_active["total"] or 0, "type": money, "hint": f"{issued_active['n']} invoice" + (f" · {issued_void['n']} dibatalkan" if issued_void["n"] else "")},
            {"key": "received", "label": "Pembayaran terverifikasi", "value": net, "type": money, "hint": f"Bruto {format_idr(gross)}" + (f", reversal {format_idr(reversed_total)}" if reversed_total else "")},
            {"key": "outstanding", "label": "Piutang jamaah", "value": outstanding, "type": money, "hint": f"Lewat jatuh tempo {format_idr(sum(v for k, v in aging_totals.items() if k != 'current'))}"},
            {"key": "expenses", "label": "Pengeluaran", "value": spent, "type": money, "hint": f"{len(period_expenses)} transaksi"},
            {"key": "cash_net", "label": "Kas bersih periode", "value": cash_net, "type": money, "hint": "Masuk − reversal − pengeluaran"},
        ],
        sections=[
            _section("receipts", "Penerimaan pembayaran", [_col("kind", "Jenis"), _col("count", "Transaksi", "int"), _col("amount_idr", "Nominal", money)], receipts_rows,
                     totals={"kind": "Bersih", "count": len(period_payments), "amount_idr": net}, description="Diakui saat diverifikasi; reversal mengurangi pada tanggal reversal."),
            _section("cash", "Kas & bank per rekening", [_col("account", "Rekening"), _col("opening_idr", "Saldo awal", money), _col("inflow_idr", "Masuk", money),
                     _col("reversal_idr", "Reversal", money), _col("expense_idr", "Pengeluaran", money), _col("closing_idr", "Saldo akhir", money)], cash_rows,
                     totals={"account": "Total", **_sum(cash_rows, "opening_idr", "inflow_idr", "reversal_idr", "expense_idr", "closing_idr")},
                     description="Saldo dihitung dari pembayaran terverifikasi dan pengeluaran yang dicatat di Umrovia (bukan mutasi rekening bank)."),
            _section("aging", "Umur piutang", [_col("bucket", "Umur"), _col("amount_idr", "Sisa tagihan", money)],
                     [{"bucket": label, "amount_idr": aging_totals[key]} for key, label, *_ in AGING], totals={"bucket": "Total", "amount_idr": sum(aging_totals.values())}),
            _section("receivables", "Rincian piutang", [_col("invoice_number", "Invoice"), _col("booking_code", "Booking"), _col("buyer", "Pelanggan"), _col("due_at", "Jatuh tempo", "date"),
                     _col("total_idr", "Total", money), _col("paid_idr", "Terbayar", money), _col("balance_idr", "Sisa", money), _col("overdue_days", "Terlambat (hari)", "int"), _col("aging", "Umur")],
                     ar_rows, totals={"invoice_number": "Total", **_sum(ar_rows, "total_idr", "paid_idr", "balance_idr")}, truncated=truncated_ar),
            _section("expense_categories", "Pengeluaran per kategori", [_col("category", "Kategori"), _col("count", "Transaksi", "int"), _col("amount_idr", "Nominal", money)], category_rows,
                     totals={"category": "Total", **_sum(category_rows, "count", "amount_idr")}),
            _section("expense_departures", "Pengeluaran per keberangkatan", [_col("departure", "Keberangkatan"), _col("count", "Transaksi", "int"), _col("amount_idr", "Nominal", money)], expense_dep_rows,
                     totals={"departure": "Total", **_sum(expense_dep_rows, "count", "amount_idr")}),
            _section("margin", "Margin estimasi per keberangkatan", [_col("departure", "Keberangkatan"), _col("start_at", "Berangkat", "date"), _col("sales_idr", "Penjualan (invoice)", money),
                     _col("received_idr", "Diterima", money), _col("expense_idr", "Biaya tercatat", money), _col("margin_idr", "Margin estimasi", money), _col("margin_pct", "Margin", "percent"), _col("note", "Catatan")],
                     margin_rows, totals={"departure": "Total", **_sum(margin_rows, "sales_idr", "received_idr", "expense_idr", "margin_idr")},
                     description="Estimasi: penjualan dari invoice aktif dikurangi biaya yang sudah dicatat untuk keberangkatan tersebut. Bukan laporan laba rugi formal."),
        ],
        checks=checks,
    )


# -------------------------------------------------------------------- SaaS --


def saas_usage(tenant, environment, f):
    """RPT-05: statement SaaS Wallet, top-up, charge Rp50.000/jamaah, tertunda dan refund."""
    note = "SaaS Wallet adalah dana prabayar untuk biaya layanan Umrovia, terpisah dari kas/bank dan DP jamaah milik travel."
    if environment != "production":
        return _envelope("saas", "Laporan SaaS Wallet", tenant, environment, f, note="Mode demo tidak memakai SaaS Wallet atau biaya layanan.", kpis=[], sections=[], checks=[])
    zone, start, end = f["zone"], f["start_dt"], f["end_dt"]
    wallet = Wallet.objects.first()
    ledger = WalletLedger.objects.filter(wallet=wallet) if wallet else WalletLedger.objects.none()
    before = ledger.filter(created_at__lt=start).order_by("-sequence").first()
    opening = before.balance_after_idr if before else 0
    in_period = ledger.filter(created_at__gte=start, created_at__lt=end)
    sums = {kind: in_period.filter(kind=kind).aggregate(t=Sum("signed_amount_idr"))["t"] or 0 for kind in ("TOPUP", "DEBIT", "REFUND")}
    last = ledger.filter(created_at__lt=end).order_by("-sequence").first()
    ledger_closing = last.balance_after_idr if last else 0
    closing = opening + sums["TOPUP"] + sums["REFUND"] + sums["DEBIT"]
    topups = list(WalletTopup.objects.filter(status="PAID", paid_at__gte=start, paid_at__lt=end).order_by("paid_at"))
    posted = list(SaaSCharge.objects.filter(charged_at__gte=start, charged_at__lt=end, status__in=["POSTED", "REFUNDED"]).select_related("booking", "participant__pilgrim").order_by("charged_at"))
    pending = list(SaaSCharge.objects.filter(status="PENDING").select_related("booking", "participant__pilgrim").order_by("eligible_at"))
    refunds = SaaSAdjustment.objects.filter(status="APPROVED", decided_at__gte=start, decided_at__lt=end).aggregate(n=Count("id"), t=Sum("amount_idr"))
    money = "money"
    charge_rows = [{"charged_at": _local_date(c.charged_at, zone), "booking_code": c.booking.code, "pilgrim": c.participant.pilgrim.name, "status": "Direfund" if c.status == "REFUNDED" else "Terpotong", "amount_idr": c.unit_price_idr} for c in posted[:ROW_LIMIT]]
    pending_rows = [{"eligible_at": _local_date(c.eligible_at, zone), "booking_code": c.booking.code, "pilgrim": c.participant.pilgrim.name, "amount_idr": c.unit_price_idr} for c in pending[:ROW_LIMIT]]
    topup_rows = [{"paid_at": _local_date(t.paid_at, zone), "number": f"TOP-{t.pk}", "provider": "Midtrans" if t.provider == "midtrans" else "Transfer manual", "amount_idr": t.amount_idr} for t in topups]
    posted_total = sum(c.unit_price_idr for c in posted)
    return _envelope(
        "saas", "Laporan SaaS Wallet", tenant, environment, f, note=note,
        kpis=[
            {"key": "balance", "label": "Saldo wallet saat ini", "value": wallet.balance_cached_idr if wallet else 0, "type": money, "hint": "Dana prabayar layanan Umrovia"},
            {"key": "topups", "label": "Top-up periode", "value": sum(t.amount_idr for t in topups), "type": money, "hint": f"{len(topups)} top-up"},
            {"key": "charges", "label": "Biaya layanan periode", "value": posted_total, "type": money, "hint": f"{len(posted)} booking-jamaah"},
            {"key": "pending", "label": "Biaya tertunda", "value": sum(c.unit_price_idr for c in pending), "type": money, "hint": f"{len(pending)} jamaah menunggu saldo"},
            {"key": "refunds", "label": "Refund disetujui", "value": refunds["t"] or 0, "type": money, "hint": f"{refunds['n']} refund"},
        ],
        sections=[
            _section("statement", "Statement wallet", [_col("item", "Keterangan"), _col("amount_idr", "Nominal", money)], [
                {"item": "Saldo awal", "amount_idr": opening}, {"item": "Top-up", "amount_idr": sums["TOPUP"]},
                {"item": "Refund biaya layanan", "amount_idr": sums["REFUND"]}, {"item": "Biaya layanan (debit)", "amount_idr": sums["DEBIT"]},
            ], totals={"item": "Saldo akhir", "amount_idr": closing}),
            _section("topups", "Top-up masuk", [_col("paid_at", "Tanggal", "date"), _col("number", "Nomor"), _col("provider", "Metode"), _col("amount_idr", "Nominal", money)], topup_rows,
                     totals={"number": "Total", **_sum(topup_rows, "amount_idr")}),
            _section("charges", "Biaya layanan per booking-jamaah", [_col("charged_at", "Dipotong", "date"), _col("booking_code", "Booking"), _col("pilgrim", "Jamaah"), _col("status", "Status"), _col("amount_idr", "Biaya", money)],
                     charge_rows, totals={"booking_code": "Total", **_sum(charge_rows, "amount_idr")}, truncated=len(posted) > ROW_LIMIT),
            _section("pending", "Biaya tertunda (saat ini)", [_col("eligible_at", "DP terverifikasi", "date"), _col("booking_code", "Booking"), _col("pilgrim", "Jamaah"), _col("amount_idr", "Biaya", money)],
                     pending_rows, totals={"booking_code": "Total", **_sum(pending_rows, "amount_idr")}, truncated=len(pending) > ROW_LIMIT),
        ],
        checks=[
            {"label": "Saldo akhir statement = saldo ledger", "ok": closing == ledger_closing, "detail": f"Statement {_rp(closing)} · ledger {_rp(ledger_closing)}"},
            {"label": "Top-up dibayar = kredit top-up di ledger", "ok": sum(t.amount_idr for t in topups) == sums["TOPUP"], "detail": f"Top-up {_rp(sum(t.amount_idr for t in topups))} · ledger {_rp(sums['TOPUP'])}"},
            {"label": "Biaya dipotong = debit ledger", "ok": posted_total == -sums["DEBIT"], "detail": f"Biaya {_rp(posted_total)} · ledger {_rp(-sums['DEBIT'])}"},
        ],
    )


BUILDERS = {"operational": operational, "finance": finance, "saas": saas_usage}
PERMISSIONS = {"operational": "reports.read", "finance": "reports.finance", "saas": "wallet.read"}
