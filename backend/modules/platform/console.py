"""Layanan konsol platform (S18): metadata & agregat tenant, lifecycle, trial, tarif, audit.

Batas data (Spec §3 "no PII leakage"): konsol hanya mengembalikan metadata
tenant (nama usaha, status, kuota, hitungan) dan angka agregat. Tidak ada
nama/kontak/NIK/paspor/dokumen jamaah; email pengguna travel ditampilkan
tersamar; isi audit melewati allowlist kunci.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from modules.audit.models import AuditEvent
from modules.audit.services import log_event
from modules.billing.models import SaaSAdjustment, SaaSCharge, SaaSPriceVersion
from modules.booking.models import Booking, BookingParticipant
from modules.platform.models import SupportTicket, TenantLifecycleRequest
from modules.tenants.models import MembershipStatus, Tenant, TenantMembership, TenantState
from modules.trial.models import TenantTrial, TrialEventType, TrialStatus
from modules.wallet.models import Wallet, WalletTopup
from modules.wallet.services import platform_tenant_context

SUSPENDABLE = {TenantState.TRIAL, TenantState.ACTIVE, TenantState.RESTRICTED}
INACTIVE_BOOKINGS = {"DRAFT", "CANCELED", "EXPIRED"}
# Audit: hanya nilai dengan kunci aman yang ditampilkan ke platform (teks bebas bisa memuat nama).
SAFE_AUDIT_KEYS = {
    "amount_idr", "total_idr", "unit_price_idr", "status", "state", "format", "kind", "version", "version_no", "rows",
    "environment", "days", "pii", "template", "type", "method", "category", "count", "participants", "eligible_participants",
    "simulated", "trigger", "resend_count", "price_version", "seat_capacity", "decision", "provider", "code", "number",
}


def mask_email(email: str) -> str:
    name, _, domain = (email or "").partition("@")
    return f"{name[:2]}{'•' * max(len(name) - 2, 1)}@{domain}" if domain else ""


def _tenant(tenant_id) -> Tenant:
    tenant = Tenant.objects.filter(pk=tenant_id).first()
    if tenant is None:
        raise NotFound("Travel tidak ditemukan.")
    return tenant


def _trial_payload(trial):
    if trial is None:
        return None
    return {
        "status": trial.status, "started_at": trial.started_at.isoformat(), "ends_at": trial.ends_at.isoformat(),
        "converted_at": trial.converted_at.isoformat() if trial.converted_at else None,
        "dummy_used": trial.dummy_count, "dummy_limit": trial.dummy_booking_limit,
    }


def _usage(tenant) -> dict:
    """Hitungan & saldo di konteks RLS tenant — angka saja, tanpa baris data jamaah."""
    with platform_tenant_context(tenant.pk):
        wallet = Wallet.objects.first()
        pending = SaaSCharge.objects.filter(status="PENDING").aggregate(n=Count("id"), t=Sum("unit_price_idr"))
        posted = SaaSCharge.objects.filter(status__in=["POSTED", "REFUNDED"]).aggregate(n=Count("id"))
        bookings = Booking.objects.filter(environment="production").exclude(status__in=INACTIVE_BOOKINGS).count()
        participants = BookingParticipant.objects.filter(booking__environment="production").exclude(booking__status__in=INACTIVE_BOOKINGS).count()
    return {
        "wallet_balance_idr": wallet.balance_cached_idr if wallet else 0, "wallet_status": wallet.status if wallet else None,
        "pending_charges": pending["n"], "pending_charge_idr": pending["t"] or 0, "posted_charges": posted["n"],
        "active_bookings": bookings, "active_participants": participants,
    }


def tenant_row(tenant, *, usage=True) -> dict:
    owner = TenantMembership.objects.without_tenant_guard().filter(tenant=tenant, role__name="Owner", status=MembershipStatus.ACTIVE).select_related("user").order_by("created_at").first()
    row = {
        "id": str(tenant.pk), "slug": tenant.slug, "display_name": tenant.display_name, "legal_name": tenant.legal_name,
        "state": tenant.state, "state_label": tenant.get_state_display(), "created_at": tenant.created_at.isoformat(),
        "active_at": tenant.active_at.isoformat() if tenant.active_at else None,
        "suspended_at": tenant.suspended_at.isoformat() if tenant.suspended_at else None, "suspension_reason": tenant.suspension_reason,
        "terminated_at": tenant.terminated_at.isoformat() if tenant.terminated_at else None,
        "owner_email": mask_email(owner.user.email) if owner else "",
        "members": TenantMembership.objects.without_tenant_guard().filter(tenant=tenant, status=MembershipStatus.ACTIVE).count(),
        "environments": sorted(tenant.environments.filter(state="ACTIVE").values_list("environment", flat=True)),
        "trial": _trial_payload(TenantTrial.objects.filter(tenant=tenant).first()),
    }
    if usage:
        row["usage"] = _usage(tenant)
    return row


def tenant_detail(tenant_id, actor) -> dict:
    tenant = _tenant(tenant_id)
    data = tenant_row(tenant)
    data["members_detail"] = [
        {"email": mask_email(m.user.email), "role": m.role.name if m.role else None, "status": m.status, "joined_at": m.created_at.isoformat()}
        for m in TenantMembership.objects.without_tenant_guard().filter(tenant=tenant).select_related("user", "role").order_by("created_at")
    ]
    data["lifecycle_requests"] = [lifecycle_payload(r) for r in TenantLifecycleRequest.objects.filter(tenant=tenant)[:10]]
    # Tindakan yang mengubah sesuatu; catatan "dilihat" tetap tersedia di halaman Audit.
    history = AuditEvent.objects.filter(tenant=tenant, action__startswith="platform.").exclude(action="platform.tenant.viewed")
    data["history"] = audit_rows(history.select_related("tenant", "actor").order_by("-occurred_at")[:20])
    data["open_tickets"] = SupportTicket.objects.filter(tenant=tenant).exclude(status=SupportTicket.Status.RESOLVED).count()
    log_event(action="platform.tenant.viewed", tenant=tenant, actor=actor, object_type="tenant", object_id=tenant.pk)
    return data


def lifecycle_payload(request) -> dict:
    return {
        "id": str(request.pk), "kind": request.kind, "status": request.status, "reason": request.reason,
        "requested_by": mask_email(request.requested_by.email), "requested_at": request.created_at.isoformat(),
        "decided_by": mask_email(request.decided_by.email) if request.decided_by else None,
        "decided_at": request.decided_at.isoformat() if request.decided_at else None, "decision_reason": request.decision_reason,
    }


def _reason(value, field="reason"):
    value = (value or "").strip()
    if len(value) < 10:
        raise ValidationError({field: "Alasan wajib diisi (minimal 10 karakter) dan tercatat di audit."})
    return value[:240]


# --------------------------------------------------------------- lifecycle --


@transaction.atomic
def suspend(tenant_id, *, actor, reason):
    reason = _reason(reason)
    tenant = Tenant.objects.select_for_update().filter(pk=tenant_id).first() or _tenant(tenant_id)
    if tenant.state not in SUSPENDABLE:
        raise ValidationError({"state": f"Travel berstatus {tenant.get_state_display()} tidak dapat ditangguhkan."})
    tenant.state_before_suspension, tenant.state = tenant.state, TenantState.SUSPENDED
    tenant.suspended_at, tenant.suspension_reason = timezone.now(), reason
    tenant.save(update_fields=["state", "state_before_suspension", "suspended_at", "suspension_reason", "updated_at"])
    log_event(action="platform.tenant.suspended", tenant=tenant, actor=actor, object_type="tenant", object_id=tenant.pk, changes={"state": TenantState.SUSPENDED, "previous": tenant.state_before_suspension, "reason": reason})
    return tenant


@transaction.atomic
def reactivate(tenant_id, *, actor, reason):
    reason = _reason(reason)
    tenant = Tenant.objects.select_for_update().filter(pk=tenant_id).first() or _tenant(tenant_id)
    if tenant.state != TenantState.SUSPENDED:
        raise ValidationError({"state": "Hanya travel yang ditangguhkan dapat diaktifkan kembali."})
    if TenantLifecycleRequest.objects.filter(tenant=tenant, status=TenantLifecycleRequest.Status.PENDING).exists():
        raise ValidationError({"state": "Ada pengajuan pengakhiran yang menunggu keputusan; putuskan dulu."})
    restored = tenant.state_before_suspension or TenantState.ACTIVE
    tenant.state, tenant.state_before_suspension, tenant.suspended_at, tenant.suspension_reason = restored, "", None, ""
    tenant.save(update_fields=["state", "state_before_suspension", "suspended_at", "suspension_reason", "updated_at"])
    log_event(action="platform.tenant.reactivated", tenant=tenant, actor=actor, object_type="tenant", object_id=tenant.pk, changes={"state": restored, "reason": reason})
    return tenant


@transaction.atomic
def request_termination(tenant_id, *, actor, reason):
    reason = _reason(reason)
    tenant = Tenant.objects.select_for_update().filter(pk=tenant_id).first() or _tenant(tenant_id)
    if tenant.state != TenantState.SUSPENDED:
        raise ValidationError({"state": "Tangguhkan travel lebih dulu sebelum mengajukan pengakhiran."})
    if TenantLifecycleRequest.objects.filter(tenant=tenant, status=TenantLifecycleRequest.Status.PENDING).exists():
        raise ValidationError({"state": "Pengajuan pengakhiran sudah ada."})
    request = TenantLifecycleRequest.objects.create(tenant=tenant, reason=reason, requested_by=actor)
    log_event(action="platform.tenant.termination_requested", tenant=tenant, actor=actor, object_type="tenant_lifecycle_request", object_id=request.pk, changes={"reason": reason})
    return request


@transaction.atomic
def decide_termination(tenant_id, request_id, *, actor, decision, reason):
    reason = _reason(reason)
    request = TenantLifecycleRequest.objects.select_for_update().filter(pk=request_id, tenant_id=tenant_id).select_related("tenant").first()
    if request is None:
        raise NotFound("Pengajuan tidak ditemukan.")
    if request.status != TenantLifecycleRequest.Status.PENDING:
        raise ValidationError({"status": "Pengajuan sudah diputuskan."})
    if request.requested_by_id == actor.pk:
        raise PermissionDenied("Pengakhiran memerlukan persetujuan admin platform lain (dua orang).")
    if decision not in {"approve", "reject"}:
        raise ValidationError({"decision": "Pilih approve atau reject."})
    tenant = Tenant.objects.select_for_update().get(pk=tenant_id)
    request.status = TenantLifecycleRequest.Status.APPROVED if decision == "approve" else TenantLifecycleRequest.Status.REJECTED
    request.decided_by, request.decided_at, request.decision_reason = actor, timezone.now(), reason
    request.save(update_fields=["status", "decided_by", "decided_at", "decision_reason", "updated_at"])
    if decision == "approve":
        tenant.state, tenant.terminated_at = TenantState.TERMINATED, timezone.now()
        tenant.save(update_fields=["state", "terminated_at", "updated_at"])
    log_event(action=f"platform.tenant.termination_{'approved' if decision == 'approve' else 'rejected'}", tenant=tenant, actor=actor, object_type="tenant_lifecycle_request", object_id=request.pk, changes={"decision": decision, "state": tenant.state, "reason": reason})
    return request


# ------------------------------------------------------------------- trial --


def trial_rows(status=""):
    qs = TenantTrial.objects.select_related("tenant").order_by("ends_at")
    if status:
        if status not in TrialStatus.values:
            raise ValidationError({"status": "Status trial tidak dikenal."})
        qs = qs.filter(status=status)
    return [{"tenant_id": str(t.tenant_id), "slug": t.tenant.slug, "display_name": t.tenant.display_name, "tenant_state": t.tenant.state, **_trial_payload(t)} for t in qs[:500]]


@transaction.atomic
def extend_trial(tenant_id, *, actor, days, reason):
    from modules.trial.services import log_trial_event

    reason = _reason(reason)
    if type(days) is not int or not 1 <= days <= 30:
        raise ValidationError({"days": "Perpanjangan 1–30 hari per pengajuan."})
    trial = TenantTrial.objects.select_for_update().filter(tenant_id=tenant_id).select_related("tenant").first()
    if trial is None:
        raise NotFound("Trial tidak ditemukan.")
    if not trial.is_running:
        raise ValidationError({"trial": "Trial sudah berakhir atau dikonversi; tidak dapat diperpanjang."})
    previous = trial.ends_at
    trial.ends_at = max(trial.ends_at, timezone.now()) + timedelta(days=days)
    trial.status = TrialStatus.EXTENDED
    trial.save(update_fields=["ends_at", "status", "updated_at"])
    log_trial_event(trial.tenant, type_=TrialEventType.EXTENDED, actor=actor, reason=reason, metadata={"days": days, "previous_ends_at": previous.isoformat(), "ends_at": trial.ends_at.isoformat()})
    log_event(action="platform.trial.extended", tenant=trial.tenant, actor=actor, object_type="tenant_trial", object_id=trial.pk, changes={"days": days, "reason": reason})
    return trial


# ----------------------------------------------------------------- pricing --


def price_rows():
    now = timezone.now()
    current = SaaSPriceVersion.objects.filter(effective_from__lte=now).order_by("-effective_from").first()
    return [{"id": str(p.pk), "code": p.code, "unit_price_idr": p.unit_price_idr, "effective_from": p.effective_from.isoformat(), "current": current is not None and p.pk == current.pk, "scheduled": p.effective_from > now} for p in SaaSPriceVersion.objects.order_by("-effective_from")]


@transaction.atomic
def publish_price(*, actor, code, unit_price_idr, effective_from, reason):
    reason = _reason(reason)
    if effective_from < timezone.now() + timedelta(hours=1):
        raise ValidationError({"effective_from": "Tarif baru berlaku paling cepat 1 jam ke depan; tarif lama tidak diubah."})
    if SaaSPriceVersion.objects.filter(code=code).exists():
        raise ValidationError({"code": "Kode versi tarif sudah dipakai."})
    price = SaaSPriceVersion.objects.create(code=code, unit_price_idr=unit_price_idr, effective_from=effective_from)
    log_event(action="platform.pricing.published", actor=actor, object_type="saas_price_version", object_id=price.pk, changes={"code": code, "unit_price_idr": unit_price_idr, "reason": reason})
    return price


# ------------------------------------------------------------------- audit --


def _safe_changes(changes, action=""):
    if not isinstance(changes, dict):
        return {}
    # Alasan yang ditulis staf platform sendiri boleh tampil; teks bebas dari tenant tidak.
    keys = SAFE_AUDIT_KEYS | ({"reason", "previous"} if action.startswith("platform.") else set())
    return {key: value for key, value in changes.items() if key in keys and isinstance(value, (int, float, bool, str)) and (not isinstance(value, str) or len(value) <= 240)}


def audit_rows(events) -> list[dict]:
    return [{
        "id": str(e.pk), "occurred_at": e.occurred_at.isoformat(), "action": e.action, "object_type": e.object_type, "object_id": e.object_id,
        "tenant": e.tenant.slug if e.tenant_id and e.tenant else None,
        "actor": mask_email(e.actor.email) if e.actor_id and e.actor else "sistem", "actor_platform": bool(e.actor_id and e.actor and e.actor.is_staff),
        "changes": _safe_changes(e.changes_json, e.action),
    } for e in events]


# ---------------------------------------------------------------- overview --


def overview() -> dict:
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    states = dict(Tenant.objects.values_list("state").annotate(n=Count("id")))
    totals = {"wallet_liability_idr": 0, "posted_month": 0, "revenue_month_idr": 0, "refunds_month_idr": 0, "pending_charges": 0, "topups_awaiting": 0, "refunds_awaiting": 0}
    for tenant in Tenant.objects.filter(environments__environment="production").distinct():
        with platform_tenant_context(tenant.pk):
            totals["wallet_liability_idr"] += Wallet.objects.aggregate(t=Sum("balance_cached_idr"))["t"] or 0
            posted = SaaSCharge.objects.filter(charged_at__gte=month_start, status__in=["POSTED", "REFUNDED"]).aggregate(n=Count("id"), t=Sum("unit_price_idr"))
            totals["posted_month"] += posted["n"]
            totals["revenue_month_idr"] += posted["t"] or 0
            totals["refunds_month_idr"] += SaaSAdjustment.objects.filter(status="APPROVED", decided_at__gte=month_start).aggregate(t=Sum("amount_idr"))["t"] or 0
            totals["pending_charges"] += SaaSCharge.objects.filter(status="PENDING").count()
            totals["topups_awaiting"] += WalletTopup.objects.filter(status="PENDING").count()
            totals["refunds_awaiting"] += SaaSAdjustment.objects.filter(status="REQUESTED").count()
    totals["revenue_month_idr"] -= totals.pop("refunds_month_idr")
    return {
        "as_of": now.isoformat(), "tenants_by_state": {state: states.get(state, 0) for state in TenantState.values},
        "trials_ending_7d": TenantTrial.objects.filter(converted_at__isnull=True, ends_at__gt=now, ends_at__lte=now + timedelta(days=7)).count(),
        "open_tickets": SupportTicket.objects.exclude(status=SupportTicket.Status.RESOLVED).count(),
        "pending_terminations": TenantLifecycleRequest.objects.filter(status=TenantLifecycleRequest.Status.PENDING).count(),
        **totals,
    }


def billing_queue() -> dict:
    """Top-up menunggu settlement & refund menunggu keputusan, lintas tenant (tanpa data jamaah)."""
    topups, refunds = [], []
    for tenant in Tenant.objects.filter(environments__environment="production").distinct().order_by("display_name"):
        with platform_tenant_context(tenant.pk):
            for t in WalletTopup.objects.filter(status="PENDING").select_related("requested_by").order_by("created_at"):
                topups.append({"tenant_id": str(tenant.pk), "tenant": tenant.display_name, "id": str(t.pk), "number": f"TOP-{t.pk}", "amount_idr": t.amount_idr, "provider": t.provider,
                               "payment_reference": t.payment_reference, "evidence_ref": t.evidence_ref, "requested_by": mask_email(t.requested_by.email), "requested_at": t.created_at.isoformat()})
            for a in SaaSAdjustment.objects.filter(status="REQUESTED").select_related("charge__booking", "requested_by").order_by("created_at"):
                refunds.append({"tenant_id": str(tenant.pk), "tenant": tenant.display_name, "id": str(a.pk), "amount_idr": a.amount_idr, "booking_code": a.charge.booking.code,
                                "reason": a.reason, "requested_by": mask_email(a.requested_by.email), "requested_at": a.created_at.isoformat()})
    return {"topups": topups, "refunds": refunds}
