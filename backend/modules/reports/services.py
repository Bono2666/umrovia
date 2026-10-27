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
from modules.travel_finance.models import ExpenseCategory, OpeningBalance, TravelExpense
from modules.travel_finance.services import ledger as cash_ledger
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
    account = params.get("account") or ""
    return {
        "from": start, "to": end, "zone": zone, "today": today,
        "start_dt": datetime.combine(start, time.min, zone), "end_dt": datetime.combine(end + timedelta(days=1), time.min, zone),
        "package": _uuid(params.get("package"), "package"), "departure": _uuid(params.get("departure"), "departure"), "status": status,
        "agent": _uuid(params.get("agent"), "agent"), "branch": _uuid(params.get("branch"), "branch"), "account": account if account == "CASH" else _uuid(account, "account"),
    }


def _envelope(kind, title, tenant, environment, f, **extra):
    return {
        "report": kind, "title": title, "travel": tenant.display_name, "environment": environment,
        "as_of": timezone.now().isoformat(), "timezone": str(f["zone"]),
        "period": {"from": f["from"].isoformat(), "to": f["to"].isoformat()},
        "filters": {key: str(f[key]) if f.get(key) else "" for key in ("package", "departure", "status", "agent", "account", "branch")},
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
    from modules.booking.models import WaitlistEntry

    waitlist = dict(WaitlistEntry.objects.filter(departure__in=deps, status="WAITING").values_list("departure_id").annotate(n=Count("id")))
    rows = []
    for dep in deps:
        ready = readiness(dep)
        rows.append({
            "departure_id": str(dep.pk), "code": dep.code, "package": dep.package.name, "package_id": str(dep.package_id),
            "start_at": _local_date(dep.start_at, f["zone"]), "status": status_label.get(dep.status, dep.status),
            "capacity": dep.seat_capacity, "seats_taken": dep.seats_taken, "available": dep.available_seats,
            "occupancy": _pct(dep.seats_taken, dep.seat_capacity), "waitlist": waitlist.get(dep.pk, 0), "bookings": bookings.get(dep.pk, 0),
            "participants": ready["participants"], "dp_received": ready["dp_received"], "confirmed": ready["confirmed"],
            "departed": departed.get(dep.pk, 0), "docs_complete": ready["docs_complete"],
            "readiness": "Lengkap" if ready["checklist_ready"] else f"Kurang {ready['gap_count']}",
            "gap_count": ready["gap_count"], "manifest": f"v{versions[dep.pk]}" if dep.pk in versions else "Belum",
        })
    counts = ("capacity", "seats_taken", "available", "waitlist", "bookings", "participants", "dp_received", "confirmed", "departed", "docs_complete", "gap_count")
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
                *count_cols, _col("waitlist", "Daftar tunggu", "int"), _col("bookings", "Booking", "int"), _col("participants", "Jamaah", "int"), _col("dp_received", "DP diterima", "int"),
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


def finance(tenant, environment, f):
    """RPT-02/04: invoice, penerimaan, reversal, piutang & aging, kas/bank, pengeluaran, margin estimasi."""
    zone, start, end = f["zone"], f["start_dt"], f["end_dt"]
    invoices = _scope_departures(TravelInvoice.objects.filter(environment=environment), f, "booking__departure__")
    payments = _scope_departures(TravelPayment.objects.filter(environment=environment, status__in=["VERIFIED", "REVERSED"], verified_at__isnull=False), f, "booking__departure__")
    reversals = _scope_departures(PaymentEvent.objects.filter(environment=environment, kind="payment.reversed"), f, "payment__booking__departure__").select_related("payment")
    expenses = TravelExpense.objects.filter(environment=environment, voided_at__isnull=True, approval_status="APPROVED")
    if f.get("branch"):
        invoices, payments = invoices.filter(booking__branch_id=f["branch"]), payments.filter(booking__branch_id=f["branch"])
        reversals, expenses = reversals.filter(payment__booking__branch_id=f["branch"]), expenses.filter(branch_id=f["branch"])
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

    # Kas/bank (MOD-11): saldo awal berotorisasi + masuk − reversal − pengeluaran ± transfer = saldo akhir.
    # Buku kas selalu per seluruh travel (atau per cabang); filter paket/keberangkatan tidak berlaku.
    cash_rows = [{k: v for k, v in row.items() if k not in ("key", "opening_as_of")} for row in cash_ledger(tenant, environment, f["from"], f["to"], branch=f.get("branch_obj"))]

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
    costs = dict(TravelExpense.objects.filter(departure_id__in=dep_ids, voided_at__isnull=True, approval_status="APPROVED").values_list("departure_id").annotate(t=Sum("amount_idr")))
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
    transfers_balanced = sum(row["transfer_in_idr"] for row in cash_rows) == sum(row["transfer_out_idr"] for row in cash_rows)
    anchored = OpeningBalance.objects.filter(environment=environment, status="APPROVED", as_of__gt=f["from"], as_of__lte=f["to"]).exists()
    checks = [
        {"label": "Piutang = total invoice − pembayaran terverifikasi teralokasi", "ok": (invoice_totals["total"] or 0) - allocated == (invoice_totals["balance"] or 0),
         "detail": f"Invoice aktif {_rp(invoice_totals['total'])} − alokasi {_rp(allocated)} = saldo {_rp(invoice_totals['balance'])}"},
        {"label": "Penerimaan periode = alokasi per jamaah", "ok": gross == allocated_period, "detail": f"Penerimaan {_rp(gross)} · alokasi {_rp(allocated_period)}"},
        {"label": "Transfer antarrekening berpasangan (masuk = keluar)", "ok": transfers_balanced, "detail": "Total kas travel tidak berubah oleh transfer"},
    ]
    if not (f["package"] or f["departure"] or anchored):
        checks.append({"label": "Mutasi kas/bank = penerimaan bersih − pengeluaran", "ok": cash_net == net - spent, "detail": f"Mutasi {_rp(cash_net)} · bersih {_rp(net)} − pengeluaran {_rp(spent)}"})
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
                     _col("reversal_idr", "Reversal", money), _col("expense_idr", "Pengeluaran", money), _col("transfer_in_idr", "Transfer masuk", money),
                     _col("transfer_out_idr", "Transfer keluar", money), _col("closing_idr", "Saldo akhir", money)], cash_rows,
                     totals={"account": "Total", **_sum(cash_rows, "opening_idr", "inflow_idr", "reversal_idr", "expense_idr", "transfer_in_idr", "transfer_out_idr", "closing_idr")},
                     description="Saldo awal berotorisasi ditambah pembayaran terverifikasi, pengeluaran disetujui dan transfer yang dicatat di Umrovia (bukan mutasi rekening bank). Tidak terpengaruh filter paket/keberangkatan."),
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


# ------------------------------------------------- penjualan / booking (MOD-13) --


def _booking_scope(qs, f, prefix=""):
    qs = _scope_departures(qs, f, f"{prefix}departure__")
    if f.get("agent"):
        qs = qs.filter(**{f"{prefix}agent_id": f["agent"]})
    if f.get("branch"):
        qs = qs.filter(**{f"{prefix}branch_id": f["branch"]})
    if f.get("branch_scope") is not None:
        qs = qs.filter(Q(**{f"{prefix}branch_id__in": f["branch_scope"]}) | Q(**{f"{prefix}branch__isnull": True}))
    return qs


def sales(tenant, environment, f):
    """MOD-13 Booking & Penjualan: booking per periode pemesanan, gross/diskon/net per paket & agen."""
    from modules.booking.services import participant_net

    zone = f["zone"]
    bookings = _booking_scope(Booking.objects.filter(environment=environment, booked_at__gte=f["start_dt"], booked_at__lt=f["end_dt"]).exclude(status="DRAFT"), f)
    bookings = list(bookings.select_related("departure__package", "agent").prefetch_related("participants__pilgrim").order_by("booked_at", "code")[: ROW_LIMIT + 1])
    truncated = len(bookings) > ROW_LIMIT
    bookings = bookings[:ROW_LIMIT]
    invoices = {i.booking_id: i for i in TravelInvoice.objects.filter(booking_id__in=[b.pk for b in bookings]).defer("pdf_data")}
    status_label = dict(Booking._meta.get_field("status").choices)
    rows, by_package, by_agent, by_status = [], defaultdict(lambda: defaultdict(int)), defaultdict(lambda: defaultdict(int)), defaultdict(lambda: {"count": 0, "pax": 0})
    for booking in bookings:
        participants = [p for p in booking.participants.all() if p.participant_status != "CANCELED" or booking.status in INACTIVE_BOOKINGS]
        gross = sum(int(p.pricing_snapshot_json.get("unit_price_idr") or 0) for p in participants)
        discount = sum(int(p.pricing_snapshot_json.get("discount_idr") or 0) for p in participants)
        extra = sum(int(p.pricing_snapshot_json.get("extra_idr") or 0) for p in participants)
        net = sum(participant_net(p.pricing_snapshot_json) for p in participants)
        invoice = invoices.get(booking.pk)
        active = booking.status not in INACTIVE_BOOKINGS
        by_status[status_label.get(booking.status, booking.status)]["count"] += 1
        by_status[status_label.get(booking.status, booking.status)]["pax"] += len(participants)
        row = {
            "booked_at": _local_date(booking.booked_at, zone), "booking_code": booking.code, "package": booking.departure.package.name,
            "departure": booking.departure.code, "agent": booking.agent.name if booking.agent_id else "Langsung",
            "payer": booking.payer_name or (participants[0].pilgrim.name if participants else ""), "pax": len(participants),
            "gross_idr": gross if active else 0, "discount_idr": discount if active else 0, "extra_idr": extra if active else 0, "net_idr": net if active else 0,
            "invoice": invoice.invoice_number if invoice else "—", "paid_idr": (invoice.total_idr - invoice.balance_idr) if invoice else 0,
            "status": status_label.get(booking.status, booking.status),
        }
        rows.append(row)
        if active:
            for bucket in (by_package[booking.departure.package.name], by_agent[row["agent"]]):
                bucket["bookings"] += 1
                for key in ("pax", "gross_idr", "discount_idr", "extra_idr", "net_idr"):
                    bucket[key] += row[key]
    package_rows = [{"package": k, **v} for k, v in sorted(by_package.items())]
    agent_rows = [{"agent": k, **v} for k, v in sorted(by_agent.items(), key=lambda item: -item[1]["net_idr"])]
    status_rows = [{"status": k, **v} for k, v in sorted(by_status.items())]
    totals = _sum(rows, "pax", "gross_idr", "discount_idr", "extra_idr", "net_idr", "paid_idr")
    active_rows = [r for r, b in zip(rows, bookings, strict=True) if b.status not in INACTIVE_BOOKINGS]
    invoiced = sum(invoices[b.pk].total_idr for b in bookings if b.pk in invoices and b.status not in INACTIVE_BOOKINGS and invoices[b.pk].status != "VOIDED")
    invoiced_net = sum(r["net_idr"] for r, b in zip(rows, bookings, strict=True) if b.pk in invoices and b.status not in INACTIVE_BOOKINGS and invoices[b.pk].status != "VOIDED")
    money = "money"
    value_cols = [_col("pax", "Jamaah", "int"), _col("gross_idr", "Gross", money), _col("discount_idr", "Diskon", money), _col("extra_idr", "Tambahan", money), _col("net_idr", "Net", money)]
    return _envelope(
        "sales", "Laporan Booking & Penjualan", tenant, environment, f,
        note="Periode berdasarkan tanggal booking. Booking batal/kedaluwarsa tetap tampil tetapi nilainya tidak dihitung dalam penjualan.",
        kpis=[
            {"key": "bookings", "label": "Booking aktif", "value": len(active_rows), "type": "int", "hint": f"{len(rows) - len(active_rows)} batal/kedaluwarsa"},
            {"key": "pax", "label": "Jamaah", "value": sum(r["pax"] for r in active_rows), "type": "int", "hint": "Peserta booking aktif"},
            {"key": "gross", "label": "Penjualan gross", "value": totals["gross_idr"], "type": money, "hint": "Harga paket sebelum penyesuaian"},
            {"key": "discount", "label": "Diskon", "value": totals["discount_idr"], "type": money, "hint": f"Tambahan {_rp(totals['extra_idr'])}"},
            {"key": "net", "label": "Penjualan net", "value": totals["net_idr"], "type": money, "hint": f"Terbayar {_rp(totals['paid_idr'])}"},
        ],
        sections=[
            _section("bookings", "Daftar booking", [_col("booked_at", "Tanggal", "date"), _col("booking_code", "Booking"), _col("package", "Paket"), _col("departure", "Keberangkatan"), _col("agent", "Agen"), _col("payer", "Pembayar"),
                     *value_cols, _col("invoice", "Invoice"), _col("paid_idr", "Terbayar", money), _col("status", "Status")],
                     rows, totals={"booking_code": "Total", **totals}, truncated=truncated),
            _section("packages", "Penjualan per paket", [_col("package", "Paket"), _col("bookings", "Booking", "int"), *value_cols], package_rows, totals={"package": "Total", **_sum(package_rows, "bookings", "pax", "gross_idr", "discount_idr", "extra_idr", "net_idr")}),
            _section("agents", "Penjualan per agen", [_col("agent", "Agen"), _col("bookings", "Booking", "int"), *value_cols], agent_rows, totals={"agent": "Total", **_sum(agent_rows, "bookings", "pax", "gross_idr", "discount_idr", "extra_idr", "net_idr")}),
            _section("statuses", "Booking per status", [_col("status", "Status"), _col("count", "Booking", "int"), _col("pax", "Jamaah", "int")], status_rows, totals={"status": "Total", **_sum(status_rows, "count", "pax")}),
        ],
        checks=[
            {"label": "Gross − diskon + tambahan = net", "ok": totals["gross_idr"] - totals["discount_idr"] + totals["extra_idr"] == totals["net_idr"], "detail": f"Net {_rp(totals['net_idr'])}"},
            {"label": "Net booking ber-invoice = total invoice aktif", "ok": invoiced_net == invoiced, "detail": f"Booking {_rp(invoiced_net)} · invoice {_rp(invoiced)}"},
        ],
    )


def payments_report(tenant, environment, f):
    """MOD-13 Pembayaran: penerimaan terverifikasi per rekening dan per petugas verifikasi."""
    zone = f["zone"]
    qs = _booking_scope(TravelPayment.objects.filter(environment=environment, verified_at__gte=f["start_dt"], verified_at__lt=f["end_dt"], status__in=["VERIFIED", "REVERSED"]), f, "booking__")
    if f.get("account") == "CASH":
        qs = qs.filter(bank_account__isnull=True)
    elif f.get("account"):
        qs = qs.filter(bank_account_id=f["account"])
    payments = list(qs.select_related("invoice", "booking", "bank_account", "created_by", "verified_by").defer("invoice__pdf_data").order_by("verified_at", "id")[: ROW_LIMIT + 1])
    truncated = len(payments) > ROW_LIMIT
    payments = payments[:ROW_LIMIT]
    name = lambda user: (user.full_name or user.email) if user else "—"  # noqa: E731
    rows, by_account, by_officer = [], defaultdict(lambda: {"count": 0, "amount_idr": 0}), defaultdict(lambda: {"count": 0, "amount_idr": 0})
    for p in payments:
        account = f"{p.bank_account.bank_name} {p.bank_account.account_masked}" if p.bank_account_id else ("Tunai" if p.method == "CASH" else "Transfer (rekening tidak dicatat)")
        amount = p.amount_idr if p.status == "VERIFIED" else 0
        rows.append({
            "verified_at": _local_date(p.verified_at, zone), "received_at": _local_date(p.received_at, zone), "invoice": p.invoice.invoice_number,
            "booking_code": p.booking.code, "payer": p.invoice.snapshot_json.get("buyer_name", ""), "kind": PAYMENT_KIND.get(p.kind, p.kind),
            "account": account, "reference": p.reference or "—", "recorded_by": name(p.created_by), "verified_by": name(p.verified_by),
            "status": "Terverifikasi" if p.status == "VERIFIED" else "Direversal", "amount_idr": amount,
        })
        if amount:
            for bucket in (by_account[account], by_officer[name(p.verified_by)]):
                bucket["count"] += 1
                bucket["amount_idr"] += amount
    total = sum(r["amount_idr"] for r in rows)
    reversed_count = sum(1 for p in payments if p.status == "REVERSED")
    account_rows = [{"account": k, **v} for k, v in sorted(by_account.items())]
    officer_rows = [{"officer": k, **v} for k, v in sorted(by_officer.items())]
    money = "money"
    return _envelope(
        "payments", "Laporan Pembayaran", tenant, environment, f,
        note="Periode berdasarkan tanggal verifikasi. Pembayaran yang kemudian direversal ditampilkan dengan nilai Rp0.",
        kpis=[
            {"key": "verified", "label": "Penerimaan terverifikasi", "value": total, "type": money, "hint": f"{len(rows) - reversed_count} pembayaran"},
            {"key": "reversed", "label": "Direversal", "value": reversed_count, "type": "int", "hint": "Pembayaran periode ini yang dibatalkan"},
            {"key": "accounts", "label": "Rekening/kas", "value": len(account_rows), "type": "int", "hint": "Tujuan penerimaan"},
            {"key": "officers", "label": "Petugas verifikasi", "value": len(officer_rows), "type": "int", "hint": "Pemeriksa dana"},
        ],
        sections=[
            _section("payments", "Rincian pembayaran", [_col("verified_at", "Diverifikasi", "date"), _col("received_at", "Diterima", "date"), _col("invoice", "Invoice"), _col("booking_code", "Booking"), _col("payer", "Pembayar"),
                     _col("kind", "Jenis"), _col("account", "Rekening"), _col("reference", "Referensi"), _col("recorded_by", "Pencatat"), _col("verified_by", "Verifikator"), _col("status", "Status"), _col("amount_idr", "Nominal", money)],
                     rows, totals={"invoice": "Total", "amount_idr": total}, truncated=truncated),
            _section("accounts", "Per rekening", [_col("account", "Rekening"), _col("count", "Pembayaran", "int"), _col("amount_idr", "Nominal", money)], account_rows, totals={"account": "Total", **_sum(account_rows, "count", "amount_idr")}),
            _section("officers", "Per petugas verifikasi", [_col("officer", "Petugas"), _col("count", "Pembayaran", "int"), _col("amount_idr", "Nominal", money)], officer_rows, totals={"officer": "Total", **_sum(officer_rows, "count", "amount_idr")}),
        ],
        checks=[
            {"label": "Total per rekening = total rincian", "ok": sum(r["amount_idr"] for r in account_rows) == total, "detail": _rp(total)},
            {"label": "Total per petugas = total rincian", "ok": sum(r["amount_idr"] for r in officer_rows) == total, "detail": _rp(total)},
        ],
    )


def commissions_report(tenant, environment, f):
    """MOD-13 Komisi: nilai estimasi, earned (layak), disetujui, dibayar per agen."""
    from modules.agents.models import Commission, CommissionStatus

    qs = _booking_scope(Commission.objects.filter(environment=environment, created_at__gte=f["start_dt"], created_at__lt=f["end_dt"]), f, "booking__")
    rows_qs = list(qs.select_related("agent", "booking__departure__package").order_by("created_at", "id")[: ROW_LIMIT + 1])
    truncated = len(rows_qs) > ROW_LIMIT
    label = dict(CommissionStatus.choices)
    by_agent = defaultdict(lambda: defaultdict(int))
    rows = []
    for c in rows_qs[:ROW_LIMIT]:
        agent = f"{c.agent.code} · {c.agent.name}"
        rows.append({
            "created_at": _local_date(c.created_at, f["zone"]), "agent": agent, "booking_code": c.booking.code, "package": c.booking.departure.package.name,
            "policy": c.policy_snapshot_json.get("name", ""), "pax": c.pax, "basis_idr": c.basis_idr, "status": label[c.status],
            "amount_idr": 0 if c.status == CommissionStatus.REVERSED else c.amount_idr, "paid_on": c.paid_on.isoformat() if c.paid_on else None,
        })
        bucket = by_agent[agent]
        bucket[c.status.lower() + "_idr"] += c.amount_idr
        if c.status in (CommissionStatus.ELIGIBLE, CommissionStatus.APPROVED, CommissionStatus.PAID):
            bucket["earned_idr"] += c.amount_idr
    agent_rows = [{"agent": k, **{key: v.get(key, 0) for key in ("estimated_idr", "earned_idr", "approved_idr", "paid_idr", "reversed_idr")}} for k, v in sorted(by_agent.items())]
    agent_totals = _sum(agent_rows, "estimated_idr", "earned_idr", "approved_idr", "paid_idr", "reversed_idr")
    paid_period = Commission.objects.filter(environment=environment, status=CommissionStatus.PAID, paid_on__gte=f["from"], paid_on__lte=f["to"])
    paid_period = _booking_scope(paid_period, f, "booking__").aggregate(n=Count("id"), t=Sum("amount_idr"))
    expense_total = TravelExpense.objects.filter(environment=environment, category="COMMISSION", voided_at__isnull=True, approval_status="APPROVED", spent_on__gte=f["from"], spent_on__lte=f["to"])
    expense_total = expense_total.aggregate(t=Sum("amount_idr"))["t"] or 0
    money = "money"
    scoped = bool(f["package"] or f["departure"] or f.get("agent") or f.get("branch") or f.get("branch_scope") is not None)
    return _envelope(
        "commissions", "Laporan Komisi Agen", tenant, environment, f,
        note="Komisi dikelompokkan menurut tanggal dibuat (booking direservasi). Earned = layak dibayar + disetujui + dibayar.",
        kpis=[
            {"key": "estimated", "label": "Estimasi", "value": agent_totals["estimated_idr"], "type": money, "hint": "Menunggu syarat pembayaran"},
            {"key": "earned", "label": "Earned", "value": agent_totals["earned_idr"], "type": money, "hint": "Syarat terpenuhi"},
            {"key": "approved", "label": "Disetujui (belum dibayar)", "value": agent_totals["approved_idr"], "type": money, "hint": "Siap dibayarkan"},
            {"key": "paid_period", "label": "Dibayar periode ini", "value": paid_period["t"] or 0, "type": money, "hint": f"{paid_period['n']} komisi"},
        ],
        sections=[
            _section("agents", "Ringkasan per agen", [_col("agent", "Agen"), _col("estimated_idr", "Estimasi", money), _col("earned_idr", "Earned", money), _col("approved_idr", "Disetujui", money), _col("paid_idr", "Dibayar", money), _col("reversed_idr", "Dibatalkan", money)],
                     agent_rows, totals={"agent": "Total", **agent_totals}),
            _section("commissions", "Rincian komisi", [_col("created_at", "Tanggal", "date"), _col("agent", "Agen"), _col("booking_code", "Booking"), _col("package", "Paket"), _col("policy", "Kebijakan"), _col("pax", "Jamaah", "int"),
                     _col("basis_idr", "Basis (net)", money), _col("amount_idr", "Komisi", money), _col("status", "Status"), _col("paid_on", "Dibayar", "date")],
                     rows, totals={"agent": "Total", **_sum(rows, "pax", "basis_idr", "amount_idr")}, truncated=truncated),
        ],
        checks=[] if scoped else [
            {"label": "Komisi dibayar periode ini = pengeluaran kategori komisi", "ok": (paid_period["t"] or 0) == expense_total, "detail": f"Komisi {_rp(paid_period['t'])} · pengeluaran {_rp(expense_total)}"},
        ],
    )


def pilgrims_report(tenant, environment, f):
    """MOD-13 Jamaah: per keberangkatan (periode berangkat) — status, kategori, kesiapan dokumen & pembayaran."""
    from modules.manifest.services import manifest_rows
    from modules.pilgrims.models import PilgrimDocument

    deps = _scope_departures(Departure.objects.filter(environment=environment, start_at__gte=f["start_dt"], start_at__lt=f["end_dt"]), f)
    if f["status"]:
        deps = deps.filter(status=f["status"])
    deps = list(deps.select_related("package").order_by("start_at", "code")[:100])
    participant_label = {"AWAITING_DP": "Menunggu DP", "DP_VERIFIED_PENDING_CHARGE": "DP terverifikasi", "CONFIRMED": "Terkonfirmasi", "READY": "Siap",
                         "DEPARTED": "Berangkat", "COMPLETED": "Selesai", "REGISTERED": "Terdaftar", "REVIEW_REQUIRED": "Perlu review"}
    payment_label = {"paid": "Lunas", "partial": "Sebagian", "unpaid": "Belum bayar"}
    rows, ready = [], 0
    allowed = None
    if f.get("branch_scope") is not None:
        allowed = {str(pk) for pk in _booking_scope(Booking.objects.filter(departure__in=deps), f).values_list("pk", flat=True)}
    for dep in deps:
        entries = [e for e in manifest_rows(dep) if allowed is None or e["booking_id"] in allowed]
        pilgrim_ids = [e["pilgrim_id"] for e in entries]
        expiring = set(str(pid) for pid in PilgrimDocument.objects.filter(pilgrim_id__in=pilgrim_ids, status="APPROVED", expires_at__lt=dep.start_at.date()).values_list("pilgrim_id", flat=True))
        for e in entries:
            ok = e["docs_complete"] and e["payment_status"] == "paid" and e["pilgrim_id"] not in expiring
            ready += ok
            rows.append({
                "departure": dep.code, "start_at": _local_date(dep.start_at, f["zone"]), "booking_code": e["booking_code"], "pilgrim_code": e["pilgrim_code"],
                "name": e["name"], "gender": e["gender"] or "—", "room_type": e["room_type"] or "—",
                "status": participant_label.get(e["participant_status"], e["participant_status"]),
                "documents": "Lengkap" if e["docs_complete"] else f"Kurang {len(e['docs_missing'])}", "doc_expiry": "Kedaluwarsa sebelum berangkat" if e["pilgrim_id"] in expiring else "—",
                "payment": payment_label.get(e["payment_status"], e["payment_status"]), "balance_idr": e["balance_idr"], "readiness": "Siap" if ok else "Belum",
            })
    truncated = len(rows) > ROW_LIMIT
    rows = rows[:ROW_LIMIT]
    money = "money"
    return _envelope(
        "pilgrims", "Laporan Jamaah", tenant, environment, f,
        note="Jamaah aktif per keberangkatan dalam periode (tanggal berangkat). Siap = dokumen lengkap & berlaku, dan lunas.",
        kpis=[
            {"key": "pilgrims", "label": "Jamaah", "value": len(rows), "type": "int", "hint": f"{len(deps)} keberangkatan"},
            {"key": "ready", "label": "Siap berangkat", "value": ready, "type": "int", "hint": f"{_pct(ready, len(rows)) or 0}% dari jamaah"},
            {"key": "docs_incomplete", "label": "Dokumen belum lengkap", "value": sum(1 for r in rows if r["documents"] != "Lengkap"), "type": "int", "hint": f"{sum(1 for r in rows if r['doc_expiry'] != '—')} dokumen kedaluwarsa sebelum berangkat"},
            {"key": "balance", "label": "Sisa tagihan", "value": sum(r["balance_idr"] for r in rows), "type": money, "hint": f"{sum(1 for r in rows if r['payment'] != 'Lunas')} jamaah belum lunas"},
        ],
        sections=[_section("pilgrims", "Daftar jamaah", [
            _col("departure", "Keberangkatan"), _col("start_at", "Berangkat", "date"), _col("booking_code", "Booking"), _col("pilgrim_code", "Kode"), _col("name", "Nama"),
            _col("gender", "L/P"), _col("room_type", "Kamar"), _col("status", "Status"), _col("documents", "Dokumen"), _col("doc_expiry", "Masa berlaku"),
            _col("payment", "Pembayaran"), _col("balance_idr", "Sisa", money), _col("readiness", "Kesiapan"),
        ], rows, totals={"departure": "Total", "balance_idr": sum(r["balance_idr"] for r in rows)}, truncated=truncated)],
        checks=[],
    )


BUILDERS = {"operational": operational, "finance": finance, "saas": saas_usage, "sales": sales, "payments": payments_report, "commissions": commissions_report, "pilgrims": pilgrims_report}
PERMISSIONS = {"operational": "reports.read", "finance": "reports.finance", "saas": "wallet.read", "sales": "reports.read", "payments": "reports.finance", "commissions": "commissions.read", "pilgrims": "reports.read"}
