"""Layanan CRM (MOD-19): tahap, aktivitas, deduplikasi, konversi lead → jamaah, ringkasan funnel."""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from modules.audit.services import log_event
from modules.crm.models import OPEN_STAGES, ActivityKind, Lead, LeadActivity, LeadSource, LeadStage, generate_lead_code
from modules.pilgrims.crypto import normalize_phone
from modules.pilgrims.models import Pilgrim, generate_pilgrim_code

STAGE_LABEL = dict(LeadStage.choices)


def duplicates(*, environment, phone="", email="", exclude=None) -> dict:
    """Calon duplikat (MOD-19 deduplikasi): lead terbuka & jamaah dengan telepon/email sama."""
    phone, email = normalize_phone(phone), (email or "").strip().lower()
    if not phone and not email:
        return {"leads": [], "pilgrims": []}
    match = (Q(phone=phone) if phone else Q(pk__in=[])) | (Q(email__iexact=email) if email else Q(pk__in=[]))
    leads = Lead.objects.filter(match, environment=environment)
    if exclude:
        leads = leads.exclude(pk=exclude)
    pilgrims = Pilgrim.objects.filter(match, environment=environment)
    return {
        "leads": [{"id": str(row.pk), "code": row.code, "name": row.name, "stage": row.stage} for row in leads[:5]],
        "pilgrims": [{"id": str(row.pk), "code": row.code, "name": row.name} for row in pilgrims[:5]],
    }


def create_lead(*, tenant, environment, actor, data, allow_duplicate=False):
    data = {**data, "phone": normalize_phone(data.get("phone", "")), "email": (data.get("email") or "").strip().lower()}
    found = duplicates(environment=environment, phone=data["phone"], email=data["email"])
    if (found["leads"] or found["pilgrims"]) and not allow_duplicate:
        raise ValidationError({"duplicates": [found], "detail": "Telepon/email sudah terdaftar. Periksa data yang ada atau simpan sebagai lead baru."})
    for _ in range(5):
        try:
            with transaction.atomic():
                lead = Lead.objects.create(tenant=tenant, environment=environment, code=generate_lead_code(), created_by=actor, owner=data.pop("owner", None) or actor, **data)
            break
        except IntegrityError:
            continue
    else:
        raise ValidationError({"code": "Gagal membuat kode lead unik, coba lagi."})
    LeadActivity.objects.create(tenant=tenant, lead=lead, kind=ActivityKind.STAGE, body=f"Lead dibuat ({lead.get_source_display()})", actor=actor)
    log_event(action="leads.created", tenant=tenant, actor=actor, object_type="lead", object_id=lead.pk, changes={"code": lead.code, "source": lead.source})
    return lead


@transaction.atomic
def change_stage(lead, *, stage, actor, lost_reason=""):
    if stage not in LeadStage.values:
        raise ValidationError({"stage": "Tahap tidak dikenal."})
    if lead.stage == LeadStage.WON:
        raise ValidationError({"stage": "Lead sudah menjadi jamaah; tahap tidak dapat diubah."})
    if stage == LeadStage.WON:
        raise ValidationError({"stage": "Gunakan konversi ke jamaah untuk menandai lead berhasil."})
    reason = (lost_reason or "").strip()
    if stage == LeadStage.LOST and len(reason) < 3:
        raise ValidationError({"lost_reason": "Alasan tidak jadi wajib diisi."})
    if stage == lead.stage:
        return lead
    previous = lead.stage
    lead.stage, lead.stage_changed_at = stage, timezone.now()
    lead.lost_reason = reason if stage == LeadStage.LOST else ""
    if stage == LeadStage.LOST:
        lead.next_follow_up_at = None
    lead.save(update_fields=["stage", "stage_changed_at", "lost_reason", "next_follow_up_at", "updated_at"])
    note = f"{STAGE_LABEL[previous]} → {STAGE_LABEL[stage]}" + (f": {reason}" if reason and stage == LeadStage.LOST else "")
    LeadActivity.objects.create(tenant=lead.tenant, lead=lead, kind=ActivityKind.STAGE, body=note, actor=actor)
    log_event(action="leads.stage_changed", tenant=lead.tenant, actor=actor, object_type="lead", object_id=lead.pk, changes={"stage": stage, "previous": previous})
    return lead


@transaction.atomic
def add_activity(lead, *, kind, body, actor, next_follow_up_at=None, clear_follow_up=False):
    if kind not in {ActivityKind.NOTE, ActivityKind.CALL, ActivityKind.WHATSAPP, ActivityKind.MEETING}:
        raise ValidationError({"kind": "Jenis aktivitas tidak dikenal."})
    body = (body or "").strip()
    if not body and next_follow_up_at is None:
        raise ValidationError({"body": "Tulis catatan aktivitas atau jadwalkan follow-up."})
    if lead.stage in {LeadStage.WON, LeadStage.LOST} and next_follow_up_at:
        raise ValidationError({"next_follow_up_at": "Lead yang sudah selesai tidak perlu follow-up."})
    activity = LeadActivity.objects.create(tenant=lead.tenant, lead=lead, kind=kind, body=body, actor=actor)
    if next_follow_up_at is not None or clear_follow_up:
        lead.next_follow_up_at = next_follow_up_at
    if lead.stage == LeadStage.NEW and kind in {ActivityKind.CALL, ActivityKind.WHATSAPP, ActivityKind.MEETING}:
        lead.stage, lead.stage_changed_at = LeadStage.CONTACTED, timezone.now()  # kontak pertama
        LeadActivity.objects.create(tenant=lead.tenant, lead=lead, kind=ActivityKind.STAGE, body="Baru → Sudah dihubungi (kontak pertama)", actor=actor)
    lead.save(update_fields=["next_follow_up_at", "stage", "stage_changed_at", "updated_at"])
    return activity


@transaction.atomic
def convert(lead, *, actor, pilgrim_id=None):
    """Lead → jamaah (baru atau yang sudah ada); tahap WON. Booking dibuat dari halaman Booking."""
    lead = Lead.objects.select_for_update().get(pk=lead.pk)
    if lead.stage == LeadStage.WON and lead.converted_pilgrim_id:
        return lead, lead.converted_pilgrim
    if lead.stage == LeadStage.LOST:
        raise ValidationError({"stage": "Buka kembali lead yang tidak jadi sebelum dikonversi."})
    if pilgrim_id:
        pilgrim = Pilgrim.objects.filter(pk=pilgrim_id, environment=lead.environment).first()
        if pilgrim is None:
            raise ValidationError({"pilgrim": "Jamaah tidak ditemukan."})
    else:
        pilgrim = Pilgrim(tenant=lead.tenant, environment=lead.environment, name=lead.name, phone=lead.phone, email=lead.email, address=lead.city)
        for _ in range(5):
            pilgrim.code = generate_pilgrim_code()
            try:
                with transaction.atomic():
                    pilgrim.save()
                break
            except IntegrityError:
                continue
        else:
            raise ValidationError({"code": "Gagal membuat kode jamaah unik, coba lagi."})
        log_event(action="pilgrims.created", tenant=lead.tenant, actor=actor, object_type="pilgrim", object_id=pilgrim.pk, changes={"code": pilgrim.code, "source": "lead", "lead": lead.code})
    lead.stage, lead.stage_changed_at, lead.converted_pilgrim, lead.converted_at, lead.next_follow_up_at = LeadStage.WON, timezone.now(), pilgrim, timezone.now(), None
    lead.save(update_fields=["stage", "stage_changed_at", "converted_pilgrim", "converted_at", "next_follow_up_at", "updated_at"])
    LeadActivity.objects.create(tenant=lead.tenant, lead=lead, kind=ActivityKind.CONVERTED, body=f"Menjadi jamaah {pilgrim.code}", actor=actor)
    log_event(action="leads.converted", tenant=lead.tenant, actor=actor, object_type="lead", object_id=lead.pk, changes={"code": lead.code, "pilgrim_code": pilgrim.code, "existing": bool(pilgrim_id)})
    return lead, pilgrim


def local_day_end(tenant):
    zone = ZoneInfo(tenant.timezone or "Asia/Jakarta")
    today = timezone.now().astimezone(zone).date()
    return datetime.combine(today + timedelta(days=1), time.min, zone)


def summary(tenant, environment, queryset=None) -> dict:
    """Funnel per tahap, konversi, follow-up jatuh tempo (hari lokal travel), dan sumber (MOD-19)."""
    now = timezone.now()
    qs = (queryset if queryset is not None else Lead.objects).filter(environment=environment)
    stages = dict(qs.order_by().values_list("stage").annotate(n=Count("id")))
    won, lost = stages.get(LeadStage.WON, 0), stages.get(LeadStage.LOST, 0)
    by_source = dict(qs.order_by().values_list("source").annotate(n=Count("id")))
    won_by_source = dict(qs.filter(stage=LeadStage.WON).order_by().values_list("source").annotate(n=Count("id")))
    open_leads = qs.filter(stage__in=OPEN_STAGES)
    return {
        "stages": [{"stage": value, "label": label, "count": stages.get(value, 0)} for value, label in LeadStage.choices],
        "total": sum(stages.values()), "open": sum(stages.get(s, 0) for s in OPEN_STAGES),
        "conversion_rate": round(won * 100 / (won + lost), 1) if won + lost else None,
        "follow_up_overdue": open_leads.filter(next_follow_up_at__lt=now).count(),
        "follow_up_today": open_leads.filter(next_follow_up_at__gte=now, next_follow_up_at__lt=local_day_end(tenant)).count(),
        "sources": [{"source": value, "label": label, "count": by_source.get(value, 0), "won": won_by_source.get(value, 0)} for value, label in LeadSource.choices if by_source.get(value)],
    }

