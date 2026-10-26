"""S16: notifikasi email/portal — outbox transaksional, dedupe, retry/backoff, DLQ, template, inbox."""
from datetime import timedelta
from smtplib import SMTPException
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core import mail
from django.db import connection
from django.test import Client
from django.utils import timezone

from modules.audit.models import AuditEvent
from modules.notifications import services
from modules.notifications.models import Notification, NotificationJob
from modules.payments.models import TravelPayment
from modules.pilgrims.models import Pilgrim, PilgrimDocument
from modules.trial.models import TenantTrialEvent
from modules.wallet.services import platform_tenant_context

from .test_payment_security import staff
from .test_payments import ok, post
from .test_payments import patch as http_patch
from .test_payments import scenario as scenario
from .test_portal import portal, upload
from .test_trial import trial_a as trial_a


@pytest.fixture(autouse=True)
def mail_settings(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "Umrovia <info@umrovia.test>"
    settings.NOTIFICATION_RETRY_DELAYS = "60,300"


def rows(**filters):
    return Notification.objects.without_tenant_guard().filter(**filters)


def set_emails(s):
    for index, pilgrim in enumerate(s["pilgrims"]):
        Pilgrim.objects.without_tenant_guard().filter(pk=pilgrim["id"]).update(email=f"jamaah{index}@example.test")


def pay(s, index, amount):
    line = s["invoice"]["lines"][index]
    payment = ok(post(s["client"], "/api/v1/payments", {
        "invoice": s["invoice"]["id"], "amount_idr": amount, "kind": "DP", "method": "CASH",
        "received_at": timezone.now().isoformat(), "reference": f"REF-{uuid4().hex[:10]}",
        "allocations": [{"booking_participant_id": line["participant_id"], "amount_idr": amount}],
        "simulate": s["environment"] == "demo",
    }))
    return payment, ok(post(s["client"], f"/api/v1/payments/{payment['id']}/verify"))


def run_queue():
    """Jalankan semua job yang jatuh tempo (worker satu putaran)."""
    NotificationJob.objects.update(due_at=timezone.now() - timedelta(seconds=1))
    return services.process_queue()


@pytest.fixture
def prod(scenario):
    s = scenario(environment="production")
    set_emails(s)
    return s


def test_tables_enforce_rls_and_queue_is_ids_only(db):
    with connection.cursor() as cursor:
        for table, expected in [("notifications_notification", (True, True)), ("notifications_notificationtemplate", (True, True)), ("notifications_notificationjob", (False, False))]:
            cursor.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=%s", [table])
            assert cursor.fetchone() == expected, table
    assert {f.name for f in NotificationJob._meta.get_fields()} == {"id", "tenant", "due_at", "created_at"}


def test_booking_and_invoice_notify_each_pilgrim_once(scenario):
    s = scenario(environment="production")  # jamaah tanpa email → portal saja
    reserved = rows(template_key="booking.reserved")
    assert reserved.count() == 3 and set(reserved.values_list("channel", flat=True)) == {"IN_APP"}
    assert set(reserved.values_list("status", flat=True)) == {"SENT"}
    invoices = {row.recipient_id: row for row in rows(template_key="invoice.issued")}
    assert len(invoices) == 3
    first = invoices[next(iter(invoices))]
    assert s["invoice"]["invoice_number"] in first.subject and "Jatuh tempo" in first.body
    own = {str(p["id"]): line["amount_idr"] for p, line in zip(s["pilgrims"], s["invoice"]["lines"], strict=True)}
    for pilgrim_id, row in invoices.items():
        assert f"Rp{own[str(pilgrim_id)]:,}".replace(",", ".") in row.body  # tagihan sendiri, bukan total grup
    ok(post(s["client"], f"/api/v1/bookings/{s['booking']['id']}/issue-invoice"))  # idempoten
    from modules.booking.models import Booking

    with platform_tenant_context(s["tenant"].pk):
        services.booking_reserved(Booking.objects.get(pk=s["booking"]["id"]))  # event diproses ulang
    assert rows(template_key="invoice.issued").count() == 3 and rows(template_key="booking.reserved").count() == 3
    assert NotificationJob.objects.count() == 0


def test_payment_verified_queues_email_once_and_worker_sends(prod):
    line = prod["invoice"]["lines"][0]
    payment, _ = pay(prod, 0, line["amount_idr"])
    ok(post(prod["client"], f"/api/v1/payments/{payment['id']}/verify"))  # verifikasi ulang: tidak ada pesan baru
    verified = rows(template_key="payment.verified")
    assert sorted(verified.values_list("channel", flat=True)) == ["EMAIL", "IN_APP"]
    assert sorted(rows(template_key="payment.settled").values_list("channel", flat=True)) == ["EMAIL", "IN_APP"]
    email = verified.get(channel="EMAIL")
    assert email.status == "PENDING" and email.recipient_email == "jamaah0@example.test"
    assert "Sisa tagihan: Rp0" in email.body and "KWT" in email.body
    # Charge SaaS tertunda (wallet kosong) → alert owner, juga satu kali.
    assert rows(template_key="saas.charge.pending", recipient_type="USER").count() == 1
    mail.outbox.clear()
    result = run_queue()
    assert result["sent"] == 3 and NotificationJob.objects.count() == 0  # verified + lunas + alert owner
    assert sorted(m.to[0].lower() for m in mail.outbox) == ["jamaah0@example.test", "jamaah0@example.test", "owner@example.com"]
    message = next(m for m in mail.outbox if m.subject == email.subject)
    assert message.from_email == "Travel A via Umrovia <info@umrovia.test>" and message.extra_headers["Auto-Submitted"] == "auto-generated"
    email.refresh_from_db()
    assert email.status == "SENT" and email.attempts == 1 and email.sent_at
    assert run_queue() == {"sent": 0, "failed": 0, "dead": 0, "skipped": 0}
    assert len(mail.outbox) == 3


def test_ntf01_provider_failure_retries_then_dead_letters_payment_untouched(prod):
    payment, _ = pay(prod, 1, 1_000_000)
    email = rows(template_key="payment.verified", channel="EMAIL").get()
    with patch("django.core.mail.EmailMessage.send", side_effect=SMTPException("down")):
        assert run_queue()["failed"] >= 1
        email.refresh_from_db()
        assert email.status == "FAILED" and email.attempts == 1 and email.last_error == "SMTPException"
        job = NotificationJob.objects.get(pk=email.pk)
        assert 50 <= (job.due_at - timezone.now()).total_seconds() <= 61  # backoff pertama 60 detik
        assert services.process_queue()["failed"] == 0  # belum jatuh tempo
        run_queue()
        run_queue()
    email.refresh_from_db()
    assert email.status == "DEAD" and email.attempts == 3 and not NotificationJob.objects.filter(pk=email.pk).exists()
    assert TravelPayment.objects.without_tenant_guard().get(pk=payment["id"]).status == "VERIFIED"
    # Kirim ulang dari dead-letter: isi sama, satu baris, tercatat di audit.
    resent = ok(post(prod["client"], f"/api/v1/notifications/{email.pk}/resend"))
    assert resent["status"] == "PENDING" and resent["resend_count"] == 1
    assert post(prod["client"], f"/api/v1/notifications/{email.pk}/resend").status_code == 400  # masih antre
    mail.outbox.clear()
    run_queue()
    email.refresh_from_db()
    assert email.status == "SENT" and [m.subject for m in mail.outbox if m.to == ["jamaah1@example.test"]] == [email.subject]
    assert AuditEvent.objects.filter(action="notifications.resent").count() == 1
    in_app = rows(template_key="payment.verified", channel="IN_APP").get()
    assert post(prod["client"], f"/api/v1/notifications/{in_app.pk}/resend").status_code == 400


def test_claim_leases_jobs_so_parallel_workers_do_not_double_send(prod):
    pay(prod, 1, 1_000_000)
    NotificationJob.objects.update(due_at=timezone.now() - timedelta(seconds=1))
    first = services._claim(10)
    assert first and services._claim(10) == []  # pekerja kedua tidak mendapat job yang sama
    assert all(job.due_at <= timezone.now() for job in first)


def test_hook_failure_never_breaks_payment(prod):
    with patch("modules.notifications.services.compose", side_effect=RuntimeError("template rusak")):
        payment, verified = pay(prod, 2, 1_000_000)
    assert verified["status"] == "VERIFIED"
    assert not rows(template_key="payment.verified").exists()


def test_document_review_and_schedule_change_notify_affected_pilgrims(prod):
    client, access_id, _ = portal(prod, 0)
    assert upload(client, access_id).status_code == 201
    doc = PilgrimDocument.objects.without_tenant_guard().get()
    ok(http_patch(prod["client"], f"/api/v1/pilgrims/{prod['pilgrims'][0]['id']}/documents/{doc.pk}", {"status": "REJECTED", "reason": "Foto buram"}))
    rejected = rows(template_key="document.rejected", channel="EMAIL").get()
    assert "Paspor" in rejected.subject and "Alasan: Foto buram" in rejected.body
    url = f"/api/v1/departures/{prod['departure']['id']}"
    ok(http_patch(prod["client"], url, {"meeting_point": "Terminal 3 Soekarno-Hatta"}))
    changed = rows(template_key="departure.changed", channel="IN_APP")
    assert changed.count() == 3 and all("titik kumpul" in row.body and "Terminal 3" in row.body for row in changed)
    ok(http_patch(prod["client"], url, {"meeting_point": "Terminal 3 Soekarno-Hatta", "notes": "catatan internal"}))
    assert rows(template_key="departure.changed").count() == 6  # 3 portal + 3 email, tidak bertambah


def test_demo_never_emails_pilgrim_contacts(scenario):
    s = scenario(environment="demo")
    set_emails(s)
    pay(s, 0, 1_000_000)
    verified = rows(template_key="payment.verified")
    assert list(verified.values_list("channel", flat=True)) == ["IN_APP"]
    assert verified.get().subject.startswith("[DEMO] ")
    assert not NotificationJob.objects.exists()


def test_templates_custom_text_required_variables_and_versions(prod):
    client = prod["client"]
    listing = {t["key"]: t for t in ok(client.get("/api/v1/notification-templates"))["results"]}
    assert not listing["saas.charge.pending"]["editable"] and listing["invoice.issued"]["version"] == 1
    url = "/api/v1/notification-templates/invoice.issued"
    assert http_patch(client, url, {}).status_code == 405
    missing = client.put(url, {"subject": "Invoice", "body": "Halo {{ nama_jamaah }}"}, content_type="application/json")
    assert missing.status_code == 400 and "wajib" in str(missing.json())
    unknown = client.put(url, {"subject": "Invoice {{ nomor_invoice }}", "body": "{{ tagihan }} {{ jatuh_tempo }} {{ nik }}"}, content_type="application/json")
    assert unknown.status_code == 400 and "nik" in str(unknown.json())
    assert client.put(url, {"subject": "A\nBcc: x@y", "body": "{{ nomor_invoice }} {{ tagihan }} {{ jatuh_tempo }}"}, content_type="application/json").status_code == 400
    body = "Yth. {{ nama_jamaah }}, tagihan {{ nomor_invoice }} sebesar {{ tagihan }} jatuh tempo {{ jatuh_tempo }}."
    saved = ok(client.put(url, {"subject": "Tagihan {{ nomor_invoice }}", "body": body}, content_type="application/json"))
    assert saved["customized"] and saved["version"] == 2
    preview = ok(post(client, f"{url}/preview", {"subject": "Tagihan {{ nomor_invoice }}", "body": body}))
    assert preview["subject"] == "Tagihan INV-2026-0001" and "Ahmad Fauzi" in preview["body"] and "Pesan otomatis" in preview["body"]
    assert client.put("/api/v1/notification-templates/trial.reminder", {"subject": "x", "body": "x"}, content_type="application/json").status_code == 404
    operations = staff(prod["tenant"], "Operations")
    assert operations.get("/api/v1/notification-templates").status_code == 200
    assert operations.put(url, {"subject": "x", "body": "x"}, content_type="application/json").status_code == 403
    assert staff(prod["tenant"], "Sales").get("/api/v1/notifications").status_code == 403
    # Template baru dipakai event berikutnya, beserta versinya.
    second = ok(post(client, f"/api/v1/bookings/{prod['booking']['id']}/issue-invoice"))
    assert second["id"] == prod["invoice"]["id"]
    with platform_tenant_context(prod["tenant"].pk):
        rendered = services.compose(prod["tenant"], "production", "invoice.issued", {"nomor_invoice": "X-1", "tagihan": "Rp1", "jatuh_tempo": "1 Mei"})
    assert rendered[0] == "Tagihan X-1" and rendered[2] == 2
    reset = ok(client.delete(url))
    assert not reset["customized"] and reset["version"] == 3 and reset["subject"] == listing["invoice.issued"]["default_subject"]
    assert AuditEvent.objects.filter(action__startswith="notifications.template.").count() == 2


def test_delivery_log_api_filters_masks_and_isolates_tenants(prod, tenant_b):
    pay(prod, 0, 1_000_000)
    data = ok(prod["client"].get("/api/v1/notifications?channel=EMAIL"))
    assert data["count"] >= 2 and all(row["channel"] == "EMAIL" for row in data["results"])
    assert data["summary"]["PENDING"] >= 2
    row = next(r for r in data["results"] if r["template_key"] == "payment.verified")
    assert row["recipient_email"].startswith("ja") and "jamaah0@" not in row["recipient_email"]
    detail = ok(prod["client"].get(f"/api/v1/notifications/{row['id']}"))
    assert "Nomor kuitansi" in detail["body"]
    assert prod["client"].get("/api/v1/notifications?status=BOGUS").status_code == 400
    other = staff(tenant_b, "Owner")
    assert ok(other.get("/api/v1/notifications"))["count"] == 0
    assert other.get(f"/api/v1/notifications/{row['id']}").status_code == 404
    assert post(other, f"/api/v1/notifications/{row['id']}/resend").status_code == 404


def test_portal_inbox_shows_only_own_messages(prod):
    pay(prod, 1, 1_000_000)
    client, access_id, _ = portal(prod, 0)
    inbox = ok(client.get("/api/v1/portal/notifications"))
    events = {item["event_type"] for item in inbox["results"]}
    assert events == {"booking.reserved", "invoice.issued"}  # pembayaran jamaah lain tidak terlihat
    assert inbox["unread"] == 2 and all(item["access_id"] == access_id for item in inbox["results"])
    first = inbox["results"][0]["id"]
    assert ok(post(client, f"/api/v1/portal/accesses/{access_id}/notifications/{first}/read"))["read_at"]
    other = rows(template_key="payment.verified", channel="IN_APP").get()
    assert post(client, f"/api/v1/portal/accesses/{access_id}/notifications/{other.pk}/read").status_code == 404
    assert ok(post(client, "/api/v1/portal/notifications/read-all"))["updated"] == 1
    assert ok(client.get("/api/v1/portal/notifications"))["unread"] == 0
    assert Client().get("/api/v1/portal/notifications").status_code in {401, 403}


def test_tr07_trial_reminders_once_per_recipient_and_day(trial_a):
    tenant, trial = trial_a
    trial.ends_at = timezone.now() + timedelta(days=2, hours=3)
    trial.save(update_fields=["ends_at"])
    assert services.send_trial_reminders() == 1
    assert services.send_trial_reminders() == 0
    reminder = rows(template_key="trial.reminder").get()
    assert reminder.event_type == "trial.reminder.d3" and "3 hari lagi" in reminder.subject and reminder.recipient_type == "USER"
    assert TenantTrialEvent.objects.filter(tenant=tenant, type="REMINDER_D3").count() == 1
    later = timezone.now() + timedelta(days=2)
    assert services.send_trial_reminders(now=later) == 1  # H-1: pesan logis baru
    assert rows(template_key="trial.reminder").count() == 2
    trial.ends_at = timezone.now() + timedelta(days=20)
    trial.save(update_fields=["ends_at"])
    assert services.send_trial_reminders() == 0


def test_notification_role_migration_only_upgrades_untouched_defaults(tenant_a, tenant_b):
    from importlib import import_module

    from django.apps import apps

    from modules.tenants.models import Role
    from modules.tenants.rbac import DEFAULT_ROLE_PERMISSIONS

    migration = import_module("modules.tenants.migrations.0008_notification_role_defaults")
    defaults = {name: Role.objects.create(tenant=tenant_a, name=name, permissions_json=grants) for name, grants in migration.BASELINES.items()}
    custom = Role.objects.create(tenant=tenant_b, name="Admin", permissions_json=["pilgrims.read"])
    for _ in range(2):
        with connection.schema_editor() as editor:
            migration.upgrade(apps, editor)
    for name, role in defaults.items():
        role.refresh_from_db()
        assert set(role.permissions_json) == set(DEFAULT_ROLE_PERMISSIONS[name])
    custom.refresh_from_db()
    assert custom.permissions_json == ["pilgrims.read"]
