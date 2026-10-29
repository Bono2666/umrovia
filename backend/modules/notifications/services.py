"""Antrean notifikasi transaksi (S16, NTF-01…05, Spec §11).

Alur: hook event bisnis → `_enqueue` di transaksi yang sama (outbox) → worker
`process_queue` mengklaim `NotificationJob` (SKIP LOCKED), mengirim email di
LUAR transaksi, lalu menandai SENT atau menjadwalkan ulang dengan backoff
eksponensial; setelah percobaan habis → DEAD (dead-letter, bisa dikirim ulang).

Hook dibungkus savepoint dan tidak pernah menggagalkan transaksi bisnis
(NTF-04: kegagalan notifikasi tidak membatalkan DP atau charge).
"""
import functools
import logging
import re
from datetime import timedelta
from email.utils import formataddr, parseaddr
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from modules.audit.services import log_event
from modules.documents.render import format_idr
from modules.notifications.catalog import TEMPLATES
from modules.notifications.models import (
    Channel,
    DeliveryStatus,
    Notification,
    NotificationJob,
    NotificationTemplate,
    RecipientType,
)
from modules.tenants.models import MembershipStatus, TenantMembership
from modules.wallet.services import platform_tenant_context

logger = logging.getLogger(__name__)

PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
DEPARTURE_FIELDS = {
    "start_at": "tanggal berangkat", "end_at": "tanggal kembali", "city_of_origin": "kota keberangkatan",
    "meeting_point": "titik kumpul", "route": "rute/maskapai",
}
INACTIVE_BOOKINGS = {"DRAFT", "CANCELED", "EXPIRED"}
PENDING_REASON_TEXT = {"INSUFFICIENT_FUNDS": "saldo tidak cukup", "WALLET_UNAVAILABLE": "wallet tidak tersedia"}
TRIAL_REMINDER_DAYS = (1, 3, 7)


# ------------------------------------------------------------------ format --


def format_date(value, zone, *, with_time=False):
    if value is None:
        return "-"
    if hasattr(value, "astimezone"):
        value = value.astimezone(ZoneInfo(zone or "Asia/Jakarta"))
    text = f"{value.day} {MONTHS[value.month - 1]} {value.year}"
    return f"{text}, {value:%H:%M}" if with_time and hasattr(value, "hour") else text


def portal_url():
    return f"{settings.TENANT_APP_URL.rstrip('/')}/portal"


def _one_line(value):
    return " ".join(str(value).split())


def render(text, values, *, single_line=False):
    """Ganti `{{ var }}`; variabel tak dikenal/kosong → '-'. Tidak pernah mengeksekusi kode."""
    clean = {key: (_one_line(val) if single_line else str(val)) for key, val in values.items()}
    return PLACEHOLDER.sub(lambda m: clean.get(m.group(1)) or "-", text)


def footer(tenant):
    contact = f" · {tenant.phone}" if tenant.phone else ""
    return f"\n\n—\n{tenant.display_name}{contact}\nPesan otomatis melalui {settings.BRAND_NAME}. Mohon tidak membalas email ini."


# --------------------------------------------------------------- templates --


def effective_template(key):
    definition = TEMPLATES[key]
    override = NotificationTemplate.objects.filter(key=key).first() if definition.editable else None
    customized = bool(override and override.subject)
    return {
        "subject": override.subject if customized else definition.subject,
        "body": override.body if customized else definition.body,
        "version": override.version if override else 1,
        "customized": customized,
    }


def validate_template(definition, subject, body):
    errors = {}
    subject, body = (subject or "").strip(), (body or "").strip()
    if not subject:
        errors["subject"] = "Subjek wajib diisi."
    elif len(subject) > 200 or "\n" in subject or "\r" in subject:
        errors["subject"] = "Subjek satu baris, maksimal 200 karakter."
    if not body:
        errors["body"] = "Isi pesan wajib diisi."
    elif len(body) > 4000:
        errors["body"] = "Isi pesan maksimal 4.000 karakter."
    used = set(PLACEHOLDER.findall(subject)) | set(PLACEHOLDER.findall(body))
    unknown = sorted(used - set(definition.variables))
    if unknown:
        errors["body"] = f"Variabel tidak dikenal: {', '.join(unknown)}."
    missing = [name for name in definition.required if name not in used]
    if missing and "body" not in errors:
        errors["body"] = f"Variabel wajib tidak boleh dihapus: {', '.join(missing)}."
    if errors:
        raise ValidationError(errors)
    return subject, body


def sample_values(definition, tenant):
    samples = {
        "nama_travel": tenant.display_name, "nama_jamaah": "Ahmad Fauzi", "tautan_portal": portal_url(),
        "kode_booking": "BKG-1A2B3C", "paket": "Umroh Reguler 12 Hari", "tanggal_berangkat": "12 Januari 2027, 08:00",
        "tanggal_pulang": "23 Januari 2027", "kota_asal": "Jakarta", "titik_kumpul": "Terminal 3 Soekarno-Hatta",
        "nomor_invoice": "INV-2026-0001", "tagihan": "Rp29.000.000", "jatuh_tempo": "2 November 2026",
        "nominal": "Rp10.000.000", "nomor_kuitansi": "KWT-2026-0001", "total_terbayar": "Rp10.000.000",
        "sisa_tagihan": "Rp19.000.000", "jenis_dokumen": "Paspor", "alasan": "Foto halaman identitas buram",
        "kode_keberangkatan": "DPR-1A2B3C4D", "perubahan": "tanggal berangkat", "nominal_biaya": "Rp50.000",
        "tautan_wallet": f"{settings.TENANT_APP_URL.rstrip('/')}/dashboard/wallet", "sisa_hari": "3",
        "tanggal_berakhir": "29 Oktober 2026", "tautan_dashboard": f"{settings.TENANT_APP_URL.rstrip('/')}/dashboard",
    }
    return {key: samples.get(key, label) for key, label in definition.variables.items()}


def compose(tenant, environment, key, values, template=None):
    template = template or effective_template(key)
    values = {"nama_travel": tenant.display_name, "tautan_portal": portal_url(), **values}
    subject = render(template["subject"], values, single_line=True)[:200]
    if environment == "demo":
        subject = f"[DEMO] {subject}"
    return subject, render(template["body"], values) + footer(tenant), template["version"]


# ----------------------------------------------------------------- enqueue --


def _enqueue(*, tenant, environment, event_type, source_key, key, recipient_type, recipient_id, recipient_name, email, values, channels):
    subject, body, version = compose(tenant, environment, key, values)
    now = timezone.now()
    created_rows = []
    for channel in channels:
        in_app = channel == Channel.IN_APP
        row, created = Notification.objects.get_or_create(
            tenant=tenant, source_key=source_key, template_key=key, channel=channel,
            recipient_type=recipient_type, recipient_id=recipient_id,
            defaults={
                "environment": environment, "event_type": event_type, "template_version": version,
                "recipient_name": recipient_name[:160], "recipient_email": "" if in_app else email,
                "subject": subject, "body": body,
                "status": DeliveryStatus.SENT if in_app else DeliveryStatus.PENDING,
                "sent_at": now if in_app else None, "next_attempt_at": None if in_app else now,
            },
        )
        if created:
            created_rows.append(row)
            if not in_app:
                NotificationJob.objects.create(id=row.pk, tenant_id=tenant.pk, due_at=now)
    return created_rows


def _portal_email(pilgrim, environment):
    """Email akun portal aktif jamaah — terbukti miliknya karena undangan portal sudah diterima."""
    from modules.identity.models import UserStatus
    from modules.portal.models import PortalAccess, PortalAccessStatus

    access = (PortalAccess.objects.filter(tenant_id=pilgrim.tenant_id, pilgrim_id=pilgrim.pk, environment=environment,
                                          status=PortalAccessStatus.ACTIVE, user__status=UserStatus.ACTIVE)
              .select_related("user").order_by("created_at").first())
    return access.user.email if access else ""


def notify_pilgrim(*, pilgrim, environment, event_type, source_key, key, values):
    """Portal selalu; email ke jamaah yang punya email.

    Produksi: email data jamaah. Demo: hanya ke akun portal aktif (email terbukti lewat
    undangan), sehingga workspace trial tidak bisa mengirim email ke kontak sembarang.
    """
    email = pilgrim.email if environment == "production" else _portal_email(pilgrim, environment)
    channels = [Channel.IN_APP, Channel.EMAIL] if email else [Channel.IN_APP]
    return _enqueue(
        tenant=pilgrim.tenant, environment=environment, event_type=event_type, source_key=source_key, key=key,
        recipient_type=RecipientType.PILGRIM, recipient_id=pilgrim.pk, recipient_name=pilgrim.name,
        email=email, values={"nama_jamaah": pilgrim.name, **values}, channels=channels,
    )


def owner_recipients(tenant):
    return [
        m.user for m in TenantMembership.objects.without_tenant_guard()
        .filter(tenant=tenant, status=MembershipStatus.ACTIVE, role__name="Owner", user__email_verified_at__isnull=False)
        .select_related("user").order_by("created_at")
    ]


def notify_owners(*, tenant, environment, event_type, source_key, key, values):
    rows = []
    for user in owner_recipients(tenant):
        rows += _enqueue(
            tenant=tenant, environment=environment, event_type=event_type, source_key=source_key, key=key,
            recipient_type=RecipientType.USER, recipient_id=user.pk, recipient_name=user.full_name or user.email,
            email=user.email, values=values, channels=[Channel.EMAIL],
        )
    return rows


def notify_user(*, tenant, user, event_type, source_key, key, values):
    """Email ke satu pengguna travel (mis. pembuka tiket dukungan); lingkungan "platform" tanpa awalan DEMO."""
    return _enqueue(
        tenant=tenant, environment="platform", event_type=event_type, source_key=source_key, key=key,
        recipient_type=RecipientType.USER, recipient_id=user.pk, recipient_name=user.full_name or user.email,
        email=user.email, values=values, channels=[Channel.EMAIL],
    )


def hook(fn):
    """Savepoint + telan error: notifikasi tidak boleh menggagalkan transaksi bisnis (NTF-04)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            with transaction.atomic():
                return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — dicatat tanpa PII, transaksi utama tetap jalan
            logger.error("notification hook failed; hook=%s error=%s", fn.__name__, type(exc).__name__)
            return []
    return wrapper


# ------------------------------------------------------------------- hooks --


def _departure_values(departure, zone):
    return {
        "paket": departure.package.name, "kode_keberangkatan": departure.code,
        "tanggal_berangkat": format_date(departure.start_at, zone, with_time=True),
        "tanggal_pulang": format_date(departure.end_at, zone), "kota_asal": departure.city_of_origin or "-",
        "titik_kumpul": departure.meeting_point or "-",
    }


@hook
def booking_reserved(booking):
    zone = booking.tenant.timezone
    values = {"kode_booking": booking.code, **_departure_values(booking.departure, zone)}
    rows = []
    for participant in booking.participants.exclude(participant_status="CANCELED").select_related("pilgrim"):
        rows += notify_pilgrim(pilgrim=participant.pilgrim, environment=booking.environment, event_type="booking.reserved", source_key=f"booking:{booking.pk}", key="booking.reserved", values=values)
    return rows


@hook
def invoice_issued(invoice):
    zone = invoice.tenant.timezone
    rows = []
    for line in invoice.lines.select_related("participant__pilgrim"):
        rows += notify_pilgrim(
            pilgrim=line.participant.pilgrim, environment=invoice.environment, event_type="invoice.issued",
            source_key=f"invoice:{invoice.pk}" + (f":v{invoice.version}" if invoice.version > 1 else ""), key="invoice.issued",
            values={"nomor_invoice": invoice.invoice_number, "kode_booking": invoice.booking.code, "tagihan": format_idr(line.amount_idr), "jatuh_tempo": format_date(invoice.due_at, zone)},
        )
    return rows


@hook
def payment_verified(payment, receipt):
    from modules.payments.models import InvoiceLine, PaymentAllocation

    booking = payment.booking
    rows = []
    allocations = payment.allocations.values("participant_id").annotate(total=Sum("amount_idr")).order_by("participant_id")
    for allocation in allocations:
        line = InvoiceLine.objects.select_related("participant__pilgrim").filter(invoice=payment.invoice, participant_id=allocation["participant_id"]).first()
        if line is None:
            continue
        paid = PaymentAllocation.objects.filter(participant_id=line.participant_id, payment__status="VERIFIED").aggregate(total=Sum("amount_idr"))["total"] or 0
        balance = max(line.amount_idr - paid, 0)
        common = {"pilgrim": line.participant.pilgrim, "environment": payment.environment, "source_key": f"payment:{payment.pk}"}
        rows += notify_pilgrim(
            **common, event_type="payment.verified", key="payment.verified",
            values={"nominal": format_idr(allocation["total"]), "kode_booking": booking.code, "nomor_kuitansi": receipt.receipt_no if receipt else "-", "total_terbayar": format_idr(paid), "sisa_tagihan": format_idr(balance)},
        )
        if balance == 0 and line.amount_idr > 0:
            rows += notify_pilgrim(
                **common, event_type="payment.settled", key="payment.settled",
                values={"kode_booking": booking.code, "total_terbayar": format_idr(paid), **_departure_values(booking.departure, payment.tenant.timezone)},
            )
    return rows


@hook
def document_reviewed(document):
    if document.status not in {"APPROVED", "REJECTED"}:
        return []
    key = "document.approved" if document.status == "APPROVED" else "document.rejected"
    return notify_pilgrim(
        pilgrim=document.pilgrim, environment=document.environment, event_type=key, source_key=f"document:{document.pk}", key=key,
        values={"jenis_dokumen": document.get_kind_display(), "alasan": document.reason or "-"},
    )


def departure_snapshot(departure):
    return {field: getattr(departure, field) for field in DEPARTURE_FIELDS}


@hook
def departure_changed(departure, before):
    from modules.booking.models import BookingParticipant

    changed = [label for field, label in DEPARTURE_FIELDS.items() if before.get(field) != getattr(departure, field)]
    if not changed:
        return []
    values = {**_departure_values(departure, departure.tenant.timezone), "perubahan": ", ".join(changed)}
    revision = f"departure:{departure.pk}:{departure.updated_at.isoformat()}"
    participants = (
        BookingParticipant.objects.filter(booking__departure=departure).exclude(booking__status__in=INACTIVE_BOOKINGS)
        .exclude(participant_status="CANCELED").select_related("pilgrim").order_by("id")
    )
    rows = []
    for participant in participants:
        rows += notify_pilgrim(pilgrim=participant.pilgrim, environment=departure.environment, event_type="departure.changed", source_key=revision, key="departure.changed", values=values)
    return rows


@hook
def charge_pending(charge, participant, reason):
    tenant = charge.tenant
    return notify_owners(
        tenant=tenant, environment="production", event_type="saas.charge.pending", source_key=f"saas.charge.pending:{charge.pk}", key="saas.charge.pending",
        values={"kode_booking": participant.booking.code, "nominal_biaya": format_idr(int(charge.unit_price_idr)), "alasan": PENDING_REASON_TEXT.get(reason, "saldo tidak cukup"), "tautan_wallet": f"{settings.TENANT_APP_URL.rstrip('/')}/dashboard/wallet"},
    )


def send_trial_reminders(now=None):
    """TR07: H-7/H-3/H-1 ke owner, satu pesan logis per trial × hari × penerima."""
    from modules.trial.models import TenantTrial, TenantTrialEvent, TrialStatus
    from modules.trial.services import log_trial_event

    now = now or timezone.now()
    created = 0
    trials = TenantTrial.objects.filter(converted_at__isnull=True, status__in=[TrialStatus.RUNNING, TrialStatus.EXTENDED], ends_at__gt=now, ends_at__lte=now + timedelta(days=max(TRIAL_REMINDER_DAYS))).select_related("tenant")
    for trial in trials:
        remaining = -(-(trial.ends_at - now) // timedelta(days=1))  # pembulatan ke atas
        day = next(d for d in TRIAL_REMINDER_DAYS if remaining <= d)
        with platform_tenant_context(trial.tenant_id) as tenant:
            rows = notify_owners(
                tenant=tenant, environment="demo", event_type=f"trial.reminder.d{day}", source_key=f"trial:{trial.pk}:d{day}", key="trial.reminder",
                values={"sisa_hari": remaining, "tanggal_berakhir": format_date(trial.ends_at, tenant.timezone), "tautan_dashboard": f"{settings.TENANT_APP_URL.rstrip('/')}/dashboard"},
            )
            event_type = f"REMINDER_D{day}"
            if rows and not TenantTrialEvent.objects.filter(tenant=tenant, type=event_type).exists():
                log_trial_event(tenant, type_=event_type, metadata={"recipients": len(rows)})
        created += len(rows)
    return created


# ------------------------------------------------------------------ worker --


def retry_delays():
    return [int(value) for value in str(settings.NOTIFICATION_RETRY_DELAYS).split(",") if value.strip()]


def _claim(batch):
    now = timezone.now()
    with transaction.atomic():
        jobs = list(NotificationJob.objects.select_for_update(skip_locked=True).filter(due_at__lte=now).order_by("due_at")[:batch])
        # Lease: job tak terlihat worker lain selama pengiriman; bila worker mati, job muncul lagi.
        NotificationJob.objects.filter(pk__in=[job.pk for job in jobs]).update(due_at=now + timedelta(seconds=settings.NOTIFICATION_LEASE_SECONDS))
    return jobs


def _message(row, tenant):
    _, address = parseaddr(settings.DEFAULT_FROM_EMAIL)
    sender = formataddr((_one_line(f"{tenant.display_name} via {settings.BRAND_NAME}"), address))
    return EmailMessage(
        subject=row.subject, body=row.body, from_email=sender, to=[row.recipient_email],
        headers={"Auto-Submitted": "auto-generated", "X-Umrovia-Notification": str(row.pk)},
    )


def deliver(job):
    with platform_tenant_context(job.tenant_id) as tenant:
        row = Notification.objects.filter(pk=job.pk, channel=Channel.EMAIL).first()
        if row is None or row.status not in {DeliveryStatus.PENDING, DeliveryStatus.FAILED}:
            NotificationJob.objects.filter(pk=job.pk).delete()
            return "skipped"
        message = _message(row, tenant)
    error = ""
    try:  # Panggilan SMTP di luar transaksi (Spec §2: external call tidak di dalam transaksi DB).
        if message.send() != 1:
            error = "NotSent"
    except Exception as exc:  # noqa: BLE001 — hanya nama kelas yang disimpan (tanpa PII)
        error = type(exc).__name__
    with platform_tenant_context(job.tenant_id):
        row = Notification.objects.select_for_update().get(pk=job.pk)
        row.attempts += 1
        if not error:
            row.status, row.sent_at, row.next_attempt_at, row.last_error = DeliveryStatus.SENT, timezone.now(), None, ""
            NotificationJob.objects.filter(pk=job.pk).delete()
        else:
            delays = retry_delays()
            row.last_error = error[:80]
            if row.attempts > len(delays):
                row.status, row.next_attempt_at = DeliveryStatus.DEAD, None
                NotificationJob.objects.filter(pk=job.pk).delete()
                logger.warning("notification dead-lettered; id=%s attempts=%s error=%s", row.pk, row.attempts, error)
            else:
                row.status = DeliveryStatus.FAILED
                row.next_attempt_at = timezone.now() + timedelta(seconds=delays[row.attempts - 1])
                NotificationJob.objects.filter(pk=job.pk).update(due_at=row.next_attempt_at)
        row.save(update_fields=["attempts", "status", "sent_at", "next_attempt_at", "last_error", "updated_at"])
        return row.status.lower()


def process_queue(batch=None):
    result = {"sent": 0, "failed": 0, "dead": 0, "skipped": 0}
    for job in _claim(batch or settings.NOTIFICATION_BATCH_SIZE):
        try:
            outcome = deliver(job)
        except Exception as exc:  # noqa: BLE001 — satu job rusak tidak menghentikan antrean
            logger.error("notification job failed; id=%s error=%s", job.pk, type(exc).__name__)
            continue
        result[outcome if outcome in result else "skipped"] += 1
    return result


def resend(row, actor):
    """Kirim ulang email yang sama (INV02: isi/nomor tetap, bukan pesan baru)."""
    if row.channel != Channel.EMAIL:
        raise ValidationError({"channel": "Hanya email yang dapat dikirim ulang."})
    if row.status == DeliveryStatus.PENDING:
        raise ValidationError({"status": "Pesan masih dalam antrean."})
    now = timezone.now()
    row.status, row.attempts, row.next_attempt_at, row.last_error = DeliveryStatus.PENDING, 0, now, ""
    row.resend_count += 1
    row.save(update_fields=["status", "attempts", "next_attempt_at", "last_error", "resend_count", "updated_at"])
    NotificationJob.objects.update_or_create(id=row.pk, defaults={"tenant_id": row.tenant_id, "due_at": now})
    log_event(action="notifications.resent", tenant=row.tenant, actor=actor, object_type="notification", object_id=row.pk, changes={"template": row.template_key, "resend_count": row.resend_count})
    return row
