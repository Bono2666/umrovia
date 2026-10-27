"""Dashboard KPI (PRD MOD-02): ringkasan operasional & keuangan, pengingat, grafik bulanan.

Dihitung dari catatan sumber saat diminta (sama dengan laporan RPT). Setiap
blok hanya diisi bila role memiliki izin terkait; blok lain bernilai `null`
sehingga UI menyembunyikannya. Setiap angka membawa tautan drill-down.
"""
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Count, Sum
from django.utils import timezone

from modules.booking.models import Booking, BookingParticipant, WaitlistEntry
from modules.booking.services import participant_net
from modules.departures.models import Departure, DepartureStatus
from modules.payments.models import TravelInvoice, TravelPayment
from modules.pilgrims.models import Pilgrim
from modules.tenants.rbac import has_permission, permission_list

ACTIVE = ["RESERVED", "CONFIRMED", "DOCUMENT_PROCESS", "READY_TO_DEPART", "DEPARTED", "COMPLETED"]
OPEN_INVOICES = ["ISSUED", "PARTIALLY_PAID"]
STATUS_LABEL = dict(Booking._meta.get_field("status").choices)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _month_start(day: date, offset=0) -> date:
    month = day.month - 1 + offset
    return date(day.year + month // 12, month % 12 + 1, 1)


def summary(request):
    from modules.tenants.branches import scope_filter

    tenant, grants = request.tenant, permission_list(request.membership.role)
    can = lambda permission: has_permission(grants, permission)  # noqa: E731
    from modules.tenants.environment import resolve_active_environment

    environment = resolve_active_environment(tenant)
    zone = ZoneInfo(tenant.timezone or "Asia/Jakarta")
    now = timezone.now()
    today = now.astimezone(zone).date()
    month_start = datetime.combine(today.replace(day=1), time.min, zone)
    first_month = _month_start(today, -11)
    chart_start = datetime.combine(first_month, time.min, zone)
    data = {"as_of": now.isoformat(), "environment": environment, "operations": None, "finance": None, "reminders": [], "chart": None, "upcoming": None}

    if can("bookings.read"):
        bookings = scope_filter(Booking.objects, request).filter(environment=environment)
        by_status = dict(bookings.values_list("status").annotate(n=Count("id")))
        new_this_month = bookings.filter(booked_at__gte=month_start).exclude(status="DRAFT")
        sales_rows = BookingParticipant.objects.filter(booking__in=new_this_month.exclude(status__in=["CANCELED", "EXPIRED"])).exclude(participant_status="CANCELED")
        open_deps = Departure.objects.filter(environment=environment, status=DepartureStatus.OPEN, start_at__gt=now)
        waiting = WaitlistEntry.objects.filter(environment=environment, status="WAITING")
        data["operations"] = {
            "pilgrims": Pilgrim.objects.filter(environment=environment).count() if can("pilgrims.read") else None,
            "new_bookings_month": new_this_month.count(),
            "new_pax_month": sales_rows.count(),
            "sales_estimate_month_idr": sum(participant_net(p.pricing_snapshot_json) for p in sales_rows.only("pricing_snapshot_json")),
            "bookings_by_status": [{"status": key, "label": STATUS_LABEL.get(key, key), "count": by_status.get(key, 0)} for key in ["DRAFT", *ACTIVE[:4], "CANCELED"]],
            "available_seats": sum(dep.available_seats for dep in open_deps),
            "open_departures": open_deps.count(),
            "waitlist": waiting.count(),
        }
        upcoming = list(Departure.objects.filter(environment=environment, start_at__gt=now).exclude(status__in=[DepartureStatus.CANCELED, DepartureStatus.COMPLETED]).select_related("package").order_by("start_at")[:5])
        data["upcoming"] = [{
            "id": str(dep.pk), "code": dep.code, "package_name": dep.package.name, "start_at": dep.start_at.isoformat(), "status": dep.status,
            "capacity": dep.seat_capacity, "taken": dep.seats_taken, "available": dep.available_seats,
        } for dep in upcoming]
        # Pengingat: kursi hampir habis, daftar tunggu yang bisa diproses, dokumen belum lengkap H-30.
        for dep in open_deps.select_related("package"):
            if dep.seat_capacity and dep.available_seats and dep.available_seats <= max(2, dep.seat_capacity // 10):
                data["reminders"].append({"kind": "seats", "tone": "warning", "text": f"{dep.code} · {dep.package.name}: sisa {dep.available_seats} kursi", "href": "/dashboard/keberangkatan"})
        ready = defaultdict(int)
        for entry in waiting.select_related("departure"):
            ready[entry.departure] += 1
        for dep, count in ready.items():
            if dep.available_seats > 0:
                data["reminders"].append({"kind": "waitlist", "tone": "success", "text": f"{dep.code}: {min(count, dep.available_seats)} jamaah daftar tunggu dapat diproses ({dep.available_seats} kursi kosong)", "href": "/dashboard/daftar-tunggu"})
        if can("manifest.read"):
            from modules.manifest.services import readiness

            soon = Departure.objects.filter(environment=environment, start_at__gt=now, start_at__lte=now + timedelta(days=30)).exclude(status__in=[DepartureStatus.CANCELED, DepartureStatus.DEPARTED, DepartureStatus.COMPLETED])
            from modules.pilgrims.models import PilgrimDocument

            for dep in soon[:10]:
                expired = PilgrimDocument.objects.filter(status="APPROVED", expires_at__lt=dep.start_at.date(), pilgrim__booking_participations__booking__departure=dep,
                                                         pilgrim__booking_participations__booking__status__in=ACTIVE).values("pilgrim_id").distinct().count()
                if expired:
                    data["reminders"].append({"kind": "expiry", "tone": "danger", "text": f"{dep.code}: dokumen {expired} jamaah kedaluwarsa sebelum berangkat", "href": f"/dashboard/manifest?departure={dep.pk}"})
                info = readiness(dep)
                missing = info["participants"] - info["docs_complete"]
                if missing > 0:
                    days = (dep.start_at.astimezone(zone).date() - today).days
                    data["reminders"].append({"kind": "documents", "tone": "danger" if days <= 14 else "warning", "text": f"{dep.code} berangkat {days} hari lagi: dokumen {missing} jamaah belum lengkap", "href": f"/dashboard/manifest?departure={dep.pk}"})

    if can("invoices.read"):
        invoices = scope_filter(TravelInvoice.objects, request, "booking__branch").filter(environment=environment, status__in=OPEN_INVOICES, balance_idr__gt=0)
        totals = invoices.aggregate(n=Count("id"), t=Sum("balance_idr"))
        overdue = invoices.filter(due_at__lt=today).aggregate(n=Count("id"), t=Sum("balance_idr"))
        due_soon = invoices.filter(due_at__gte=today, due_at__lte=today + timedelta(days=7)).aggregate(n=Count("id"), t=Sum("balance_idr"))
        finance = {"open_invoices": totals["n"], "receivable_idr": totals["t"] or 0, "overdue_invoices": overdue["n"], "overdue_idr": overdue["t"] or 0, "due_soon_invoices": due_soon["n"], "due_soon_idr": due_soon["t"] or 0, "payments_month_idr": None, "pending_verification": None}
        if overdue["n"]:
            data["reminders"].append({"kind": "overdue", "tone": "danger", "text": f"{overdue['n']} invoice lewat jatuh tempo, sisa {overdue['t']:,} rupiah".replace(",", "."), "href": "/dashboard/invoice"})
        if due_soon["n"]:
            data["reminders"].append({"kind": "due", "tone": "warning", "text": f"{due_soon['n']} invoice jatuh tempo dalam 7 hari", "href": "/dashboard/invoice"})
        if can("payments.read_all") or can("reports.finance"):
            payments = scope_filter(TravelPayment.objects, request, "booking__branch").filter(environment=environment)
            finance["payments_month_idr"] = payments.filter(status="VERIFIED", verified_at__gte=month_start).aggregate(t=Sum("amount_idr"))["t"] or 0
            finance["pending_verification"] = payments.filter(status="SUBMITTED").count()
            if finance["pending_verification"] and can("payments.verify"):
                data["reminders"].append({"kind": "verify", "tone": "warning", "text": f"{finance['pending_verification']} pembayaran menunggu verifikasi", "href": "/dashboard/pembayaran"})
        data["finance"] = finance

    if can("bookings.read"):
        months = [_month_start(today, offset) for offset in range(-11, 1)]
        series = {m: {"bookings": 0, "sales_idr": 0, "payments_idr": None} for m in months}
        for booking in scope_filter(Booking.objects, request).filter(environment=environment, booked_at__gte=chart_start).exclude(status__in=["DRAFT", "CANCELED", "EXPIRED"]).prefetch_related("participants"):
            key = booking.booked_at.astimezone(zone).date().replace(day=1)
            if key in series:
                series[key]["bookings"] += 1
                series[key]["sales_idr"] += sum(participant_net(p.pricing_snapshot_json) for p in booking.participants.all() if p.participant_status != "CANCELED")
        if data["finance"] and data["finance"]["payments_month_idr"] is not None:
            for m in months:
                series[m]["payments_idr"] = 0
            for p in scope_filter(TravelPayment.objects, request, "booking__branch").filter(environment=environment, status="VERIFIED", verified_at__gte=chart_start).only("amount_idr", "verified_at"):
                key = p.verified_at.astimezone(zone).date().replace(day=1)
                if key in series:
                    series[key]["payments_idr"] += p.amount_idr
        data["chart"] = [{"month": m.isoformat(), "label": f"{MONTHS[m.month - 1]} {str(m.year)[2:]}", **series[m]} for m in months]
    return data
