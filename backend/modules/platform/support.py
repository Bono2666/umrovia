"""Tiket dukungan tenant ↔ platform (S18, Spec §3 Platform Support, PRD §31).

Staf Support hanya melihat isi tiket dan metadata diagnosis (status, kuota,
hitungan) — bukan data operasional/jamaah tenant. Catatan internal tidak
pernah dikirim ke tenant. Balasan platform memberi tahu pembuka tiket lewat
antrean email (S16).
"""
import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from modules.audit.services import log_event
from modules.platform.console import mask_email
from modules.platform.models import SupportMessage, SupportTicket


def _body(value, field="body"):
    value = (value or "").strip()
    if len(value) < 5:
        raise ValidationError({field: "Tulis pesan minimal 5 karakter."})
    if len(value) > 5000:
        raise ValidationError({field: "Pesan maksimal 5.000 karakter."})
    return value


def ticket_payload(ticket, *, platform=False, messages=False) -> dict:
    data = {
        "id": str(ticket.pk), "number": ticket.number, "subject": ticket.subject, "category": ticket.category,
        "category_label": ticket.get_category_display(), "status": ticket.status, "status_label": ticket.get_status_display(),
        "priority": ticket.priority, "created_at": ticket.created_at.isoformat(), "last_message_at": ticket.last_message_at.isoformat(),
        "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        "opened_by": (mask_email(ticket.opened_by.email) if platform else (ticket.opened_by.full_name or ticket.opened_by.email)) if ticket.opened_by else None,
    }
    if platform:
        data["tenant"] = {"id": str(ticket.tenant_id), "slug": ticket.tenant.slug, "display_name": ticket.tenant.display_name, "state": ticket.tenant.state}
        data["assigned_to"] = mask_email(ticket.assigned_to.email) if ticket.assigned_to else None
    if messages:
        rows = ticket.messages.select_related("author").order_by("created_at")
        if not platform:
            rows = rows.filter(internal=False)
        data["messages"] = [{
            "id": str(m.pk), "created_at": m.created_at.isoformat(), "from_platform": m.from_platform, "internal": m.internal, "body": m.body,
            "author": ("Tim Umrovia" if not platform else mask_email(m.author.email) if m.author else "Tim Umrovia") if m.from_platform
            else ((mask_email(m.author.email) if platform else (m.author.full_name or m.author.email)) if m.author else "—"),
        } for m in rows]
    return data


@transaction.atomic
def open_ticket(*, tenant, user, subject, category, body):
    subject = (subject or "").strip()
    if not 5 <= len(subject) <= 160:
        raise ValidationError({"subject": "Judul 5–160 karakter."})
    if category not in SupportTicket.Category.values:
        raise ValidationError({"category": "Kategori tidak dikenal."})
    body = _body(body)
    for _ in range(5):
        try:
            with transaction.atomic():
                ticket = SupportTicket.objects.create(number=f"SUP-{timezone.now():%y%m}-{secrets.token_hex(3).upper()}", tenant=tenant, opened_by=user, subject=subject, category=category)
            break
        except IntegrityError:
            continue
    else:
        raise ValidationError({"number": "Gagal membuat nomor tiket, coba lagi."})
    SupportMessage.objects.create(ticket=ticket, author=user, body=body)
    log_event(action="support.ticket.opened", tenant=tenant, actor=user, object_type="support_ticket", object_id=ticket.pk, changes={"category": category, "number": ticket.number})
    return ticket


@transaction.atomic
def tenant_reply(ticket, *, user, body):
    body = _body(body)
    SupportMessage.objects.create(ticket=ticket, author=user, body=body)
    ticket.status = SupportTicket.Status.OPEN
    ticket.resolved_at = None
    ticket.last_message_at = timezone.now()
    ticket.save(update_fields=["status", "resolved_at", "last_message_at", "updated_at"])
    log_event(action="support.ticket.replied", tenant=ticket.tenant, actor=user, object_type="support_ticket", object_id=ticket.pk, changes={"number": ticket.number})
    return ticket


@transaction.atomic
def platform_reply(ticket, *, user, body, internal=False):
    body = _body(body)
    SupportMessage.objects.create(ticket=ticket, author=user, body=body, from_platform=True, internal=internal)
    fields = ["last_message_at", "updated_at"]
    ticket.last_message_at = timezone.now()
    if not internal and ticket.status != SupportTicket.Status.RESOLVED:
        ticket.status = SupportTicket.Status.WAITING_TENANT
        fields.append("status")
    if ticket.assigned_to_id is None:
        ticket.assigned_to = user
        fields.append("assigned_to")
    ticket.save(update_fields=fields)
    log_event(action="platform.support.replied", tenant=ticket.tenant, actor=user, object_type="support_ticket", object_id=ticket.pk, changes={"number": ticket.number, "type": "internal" if internal else "reply"})
    if not internal and ticket.opened_by_id:
        from modules.notifications.services import notify_user
        from modules.wallet.services import platform_tenant_context

        with platform_tenant_context(ticket.tenant_id) as tenant:
            notify_user(tenant=tenant, user=ticket.opened_by, event_type="support.replied", source_key=f"support:{ticket.pk}:{ticket.last_message_at.isoformat()}", key="support.replied",
                        values={"nomor_tiket": ticket.number, "judul": ticket.subject, "tautan_bantuan": f"{_app_url()}/dashboard/bantuan"})
    return ticket


def _app_url():
    from django.conf import settings

    return settings.TENANT_APP_URL.rstrip("/")


@transaction.atomic
def update_ticket(ticket, *, user, status=None, priority=None, assign_to_me=None):
    changes = {}
    if status is not None:
        if status not in SupportTicket.Status.values:
            raise ValidationError({"status": "Status tidak dikenal."})
        ticket.status = status
        ticket.resolved_at = timezone.now() if status == SupportTicket.Status.RESOLVED else None
        changes["status"] = status
    if priority is not None:
        if priority not in {"NORMAL", "HIGH"}:
            raise ValidationError({"priority": "Prioritas tidak dikenal."})
        ticket.priority = priority
        changes["priority"] = priority
    if assign_to_me is not None:
        ticket.assigned_to = user if assign_to_me else None
        changes["assigned"] = bool(assign_to_me)
    ticket.save()
    log_event(action="platform.support.updated" if user.is_staff else "support.ticket.updated", tenant=ticket.tenant, actor=user, object_type="support_ticket", object_id=ticket.pk, changes={"number": ticket.number, **{k: v for k, v in changes.items() if k == "status"}})
    return ticket
