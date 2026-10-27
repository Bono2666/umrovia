"""Layanan portal jamaah (S14). Object-level: setiap baca/tulis lewat `scoped_access`.

Request portal tidak membawa membership tenant. Grant `PortalAccess` (ID saja)
menentukan tenant; `platform_tenant_context` memasang RLS tenant itu dan
setiap query disaring lagi ke `pilgrim_id` grant. Data jamaah lain dalam
booking grup tidak pernah ikut keluar.
"""
import hashlib
import secrets
from contextlib import contextmanager
from datetime import timedelta
from smtplib import SMTPException
from uuid import UUID

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from modules.audit.services import log_event
from modules.booking.models import BookingParticipant
from modules.identity.models import User, UserStatus
from modules.manifest.models import DocumentRequirementDeadline
from modules.manifest.services import effective_requirements
from modules.payments.models import InvoiceLine, PaymentAllocation, TravelInvoice, TravelPayment, TravelReceipt
from modules.pilgrims.crypto import normalize_phone
from modules.pilgrims.models import Pilgrim, PilgrimDocument, PilgrimDocumentKind, PilgrimDocumentStatus
from modules.portal.files import add_uploaded_document, has_file
from modules.portal.models import PortalAccess, PortalAccessStatus, PortalInvite
from modules.tenants.environment import assert_environment_writable
from modules.tenants.models import Tenant
from modules.wallet.services import platform_tenant_context

HIDDEN_BOOKING_STATUSES = {"DRAFT", "EXPIRED"}
DEADLINE_TEXT = {"before_ready": "Sebelum siap berangkat", "before_departure": "Sebelum berangkat"}
PARTICIPANT_STEPS = ["REGISTERED", "AWAITING_DP", "DP_VERIFIED_PENDING_CHARGE", "CONFIRMED", "READY", "DEPARTED", "COMPLETED"]


class EmailUnavailable(APIException):
    status_code = 502
    default_code = "email_unavailable"


class InviteError(APIException):
    status_code = 400
    default_code = "invalid_invite"


class LoginRequired(PermissionDenied):
    default_code = "login_required"


def _sha256(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def _mask_email(email):
    name, _, domain = email.partition("@")
    return f"{name[:2]}{'•' * max(len(name) - 2, 1)}@{domain}"


# ------------------------------------------------------------------ invites --


def invite_pilgrim(*, pilgrim, email, actor):
    """Staf (konteks tenant): satu undangan terbuka per jamaah; yang lama dicabut."""
    assert_environment_writable(pilgrim.tenant, pilgrim.environment)
    email = (email or pilgrim.email or "").strip().lower()
    if not email:
        raise ValidationError({"email": "Isi email jamaah untuk mengirim undangan portal."})
    now = timezone.now()
    PortalInvite.objects.filter(pilgrim=pilgrim, used_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now)
    raw = f"{pilgrim.tenant_id}.{secrets.token_urlsafe(32)}"
    invite = PortalInvite.objects.create(
        tenant_id=pilgrim.tenant_id, pilgrim=pilgrim, environment=pilgrim.environment, email=email,
        token_sha256=_sha256(raw), expires_at=now + timedelta(days=settings.PORTAL_INVITE_TTL_DAYS), invited_by=actor,
    )
    url = f"{settings.TENANT_APP_URL.rstrip('/')}/portal/undangan?token={raw}"
    travel = pilgrim.tenant.display_name
    try:
        send_mail(
            subject=f"{travel} — akses portal jamaah Umrovia",
            message=(
                f"Assalamu'alaikum {pilgrim.name},\n\n{travel} mengundang Anda ke portal jamaah untuk melihat "
                f"jadwal keberangkatan, status pembayaran dan mengunggah dokumen perjalanan.\n\n"
                f"Buka tautan ini untuk mengaktifkan akses:\n{url}\n\n"
                f"Tautan berlaku {settings.PORTAL_INVITE_TTL_DAYS} hari dan hanya bisa dipakai sekali. "
                f"Jika Anda tidak merasa terdaftar di {travel}, abaikan email ini.\n\n— {settings.BRAND_NAME}"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
        )
    except (SMTPException, OSError):
        raise EmailUnavailable("Email undangan gagal dikirim. Periksa pengaturan email lalu coba lagi.") from None
    log_event(action="portal.invite.sent", tenant=pilgrim.tenant, actor=actor, object_type="pilgrim", object_id=pilgrim.pk, changes={"pilgrim_code": pilgrim.code})
    return invite


@contextmanager
def _invite_scope(raw):
    """Token `<tenant>.<acak>` → konteks RLS tenant tersebut + undangan terkunci."""
    tenant_part = (raw or "").split(".", 1)[0]
    try:
        tenant_id = UUID(tenant_part)
    except ValueError:
        raise InviteError("Tautan undangan tidak valid.") from None
    if not Tenant.objects.filter(pk=tenant_id).exists():
        raise InviteError("Tautan undangan tidak valid.")
    with platform_tenant_context(tenant_id) as tenant:
        invite = PortalInvite.objects.select_for_update().select_related("pilgrim").filter(token_sha256=_sha256(raw)).first()
        if invite is None:
            raise InviteError("Tautan undangan tidak valid.")
        yield tenant, invite


def _invite_problem(invite):
    if invite.used_at:
        return "used", "Undangan ini sudah dipakai. Silakan masuk dengan akun Anda."
    if invite.revoked_at:
        return "revoked", "Undangan ini sudah diganti atau dibatalkan. Minta undangan baru ke travel."
    if invite.expires_at <= timezone.now():
        return "expired", "Undangan sudah kedaluwarsa. Minta undangan baru ke travel."
    return None, ""


@transaction.atomic
def inspect_invite(raw):
    with _invite_scope(raw) as (tenant, invite):
        code, detail = _invite_problem(invite)
        return {
            "valid": code is None, "code": code, "detail": detail,
            "travel_name": tenant.display_name, "pilgrim_name": invite.pilgrim.name.split(" ")[0],
            "email": _mask_email(invite.email), "account_exists": User.objects.filter(email__iexact=invite.email).exists(),
        }


@transaction.atomic
def accept_invite(*, raw, request, password="", full_name=""):
    """Undangan → grant. Email undangan = bukti kepemilikan untuk akun baru;
    akun yang sudah ada wajib login dulu (mencegah pengambilalihan akun)."""
    with _invite_scope(raw) as (tenant, invite):
        code, detail = _invite_problem(invite)
        if code:
            raise InviteError(detail)
        user = User.objects.filter(email__iexact=invite.email).first()
        current = request.user if request.user.is_authenticated else None
        if user is not None:
            if current is None:
                raise LoginRequired("Email ini sudah punya akun Umrovia. Masuk dulu, lalu buka lagi tautan undangan.")
            if current.pk != user.pk:
                raise PermissionDenied("Undangan ini untuk email lain. Keluar lalu masuk dengan email yang diundang.")
            if user.status != UserStatus.ACTIVE:
                raise PermissionDenied("Akun tidak aktif. Hubungi travel.")
        else:
            if current is not None:
                raise PermissionDenied("Undangan ini untuk email lain. Keluar dulu untuk membuat akun jamaah.")
            try:
                validate_password(password)
            except DjangoValidationError as exc:
                raise ValidationError({"password": list(exc.messages)}) from None
            user = User.objects.create_user(email=invite.email, password=password, full_name=(full_name or invite.pilgrim.name).strip()[:150])
            user.status, user.email_verified_at = UserStatus.ACTIVE, timezone.now()
            user.save(update_fields=["status", "email_verified_at", "updated_at"])
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        access, created = PortalAccess.objects.get_or_create(
            user=user, pilgrim_id=invite.pilgrim_id,
            defaults={"tenant": tenant, "environment": invite.environment},
        )
        if not created and access.status != PortalAccessStatus.ACTIVE:
            access.status, access.revoked_at = PortalAccessStatus.ACTIVE, None
            access.save(update_fields=["status", "revoked_at", "updated_at"])
        invite.used_at, invite.accepted_by = timezone.now(), user
        invite.save(update_fields=["used_at", "accepted_by", "updated_at"])
        log_event(action="portal.invite.accepted", tenant=tenant, actor=user, object_type="pilgrim", object_id=invite.pilgrim_id, changes={"new_account": created})
        return access


def portal_status(pilgrim):
    """Staf: grant dan undangan terbuka untuk satu jamaah (konteks tenant)."""
    accesses = PortalAccess.objects.filter(tenant_id=pilgrim.tenant_id, pilgrim_id=pilgrim.pk).select_related("user").order_by("created_at")
    invite = PortalInvite.objects.filter(pilgrim=pilgrim, used_at__isnull=True, revoked_at__isnull=True, expires_at__gt=timezone.now()).first()
    return {
        "accesses": [{"id": str(a.pk), "email": a.user.email, "status": a.status, "created_at": a.created_at.isoformat()} for a in accesses],
        "pending_invite": {"id": str(invite.pk), "email": invite.email, "expires_at": invite.expires_at.isoformat()} if invite else None,
    }


@transaction.atomic
def revoke_portal(*, pilgrim, actor, access_id=None, invite_id=None):
    now = timezone.now()
    if invite_id:
        changed = PortalInvite.objects.filter(pk=invite_id, pilgrim=pilgrim, used_at__isnull=True, revoked_at__isnull=True).update(revoked_at=now)
    else:
        changed = PortalAccess.objects.filter(pk=access_id, tenant_id=pilgrim.tenant_id, pilgrim_id=pilgrim.pk, status=PortalAccessStatus.ACTIVE).update(status=PortalAccessStatus.REVOKED, revoked_at=now)
    if not changed:
        raise NotFound("Akses atau undangan portal tidak ditemukan.")
    log_event(action="portal.access.revoked", tenant=pilgrim.tenant, actor=actor, object_type="pilgrim", object_id=pilgrim.pk, changes={"access_id": str(access_id or ""), "invite_id": str(invite_id or "")})


# ------------------------------------------------------------------- scope --


def active_accesses(user):
    # Travel yang ditangguhkan/diakhiri platform: portal jamaahnya ikut tertutup (S18).
    return PortalAccess.objects.filter(user=user, status=PortalAccessStatus.ACTIVE).exclude(tenant__state__in=["SUSPENDED", "TERMINATED"]).select_related("tenant").order_by("created_at")


@contextmanager
def scoped_access(user, access_id):
    """Grant milik user → (access, pilgrim) di konteks RLS tenant-nya; selain itu 404."""
    try:
        access = active_accesses(user).filter(pk=access_id).first()
    except DjangoValidationError:
        access = None
    if access is None:
        raise NotFound("Data tidak ditemukan.")
    with platform_tenant_context(access.tenant_id):
        pilgrim = Pilgrim.objects.filter(pk=access.pilgrim_id, environment=access.environment).first()
        if pilgrim is None:
            raise NotFound("Data tidak ditemukan.")
        yield access, pilgrim


def _participants(pilgrim):
    return (
        BookingParticipant.objects.filter(pilgrim=pilgrim)
        .exclude(booking__status__in=HIDDEN_BOOKING_STATUSES)
        .select_related("booking__departure__package")
        .order_by("-booking__booked_at")
    )


def _booking_payload(participant):
    booking, departure = participant.booking, participant.booking.departure
    invoice = TravelInvoice.objects.filter(booking=booking).first()
    line = InvoiceLine.objects.filter(invoice=invoice, participant=participant).first() if invoice else None
    amount = line.amount_idr if line else int(participant.pricing_snapshot_json.get("unit_price_idr") or 0)
    paid = PaymentAllocation.objects.filter(participant=participant, payment__status="VERIFIED").aggregate(total=Sum("amount_idr"))["total"] or 0
    # PDF hanya bila seluruh isinya milik jamaah ini (dokumen grup memuat nama lain).
    solo_invoice = invoice is not None and invoice.status != "VOIDED" and not invoice.lines.exclude(participant=participant).exists()
    receipts = []
    payments = TravelPayment.objects.filter(status="VERIFIED", allocations__participant=participant).distinct().order_by("received_at")
    for payment in payments:
        own = payment.allocations.filter(participant=participant).aggregate(total=Sum("amount_idr"))["total"] or 0
        receipt = TravelReceipt.objects.filter(payment=payment).first()
        receipts.append({
            "id": str(receipt.pk) if receipt else None, "number": receipt.receipt_no if receipt else None,
            "kind": payment.kind, "amount_idr": own, "received_at": payment.received_at.isoformat(),
            "downloadable": receipt is not None and not payment.allocations.exclude(participant=participant).exists(),
        })
    step = participant.participant_status
    return {
        "booking_id": str(booking.pk), "code": booking.code, "status": booking.status,
        "participant_status": step, "progress": PARTICIPANT_STEPS.index(step) if step in PARTICIPANT_STEPS else None,
        "room_type": participant.pricing_snapshot_json.get("room_type") or "",
        "departure": {
            "code": departure.code, "package_name": departure.package.name, "start_at": departure.start_at.isoformat(),
            "end_at": departure.end_at.isoformat() if departure.end_at else None, "city_of_origin": departure.city_of_origin,
            "route": departure.route, "meeting_point": departure.meeting_point, "status": departure.status,
        },
        "payment": {
            "amount_idr": amount, "paid_idr": paid, "balance_idr": max(amount - paid, 0),
            "invoice_id": str(invoice.pk) if solo_invoice else None,
            "invoice_number": invoice.invoice_number if invoice and invoice.status != "VOIDED" else None,
            "due_at": invoice.due_at.isoformat() if invoice and invoice.status != "VOIDED" else None,
            "group_invoice": invoice is not None and not solo_invoice and invoice.status != "VOIDED",
        },
        "receipts": receipts,
    }


def _profile_payload(pilgrim):
    return {
        "name": pilgrim.name, "code": pilgrim.code, "phone": pilgrim.phone, "email": pilgrim.email, "address": pilgrim.address,
        "emergency_contact_name": pilgrim.emergency_contact_name, "emergency_contact_phone": pilgrim.emergency_contact_phone,
        "identity_masked": pilgrim.identity_masked, "passport_masked": pilgrim.passport_masked,
    }


@transaction.atomic
def overview(user):
    """Semua grant aktif: travel, profil, booking dan progres pembayaran milik sendiri."""
    result = []
    for access in active_accesses(user):
        with platform_tenant_context(access.tenant_id) as tenant:
            pilgrim = Pilgrim.objects.filter(pk=access.pilgrim_id, environment=access.environment).first()
            if pilgrim is None:
                continue
            result.append({
                "access_id": str(access.pk), "travel": {"name": tenant.display_name, "phone": tenant.phone},
                "environment": access.environment, "profile": _profile_payload(pilgrim),
                "bookings": [_booking_payload(p) for p in _participants(pilgrim)],
                "announcements": announcements_for(pilgrim),
                "change_requests": [change_request_payload(r) for r in pilgrim.change_requests.all()[:5]],
            })
    return result


# --------------------------------------------------------------- documents --


def _document_payload(doc):
    return {
        "id": str(doc.pk), "version": doc.version, "status": doc.status, "reason": doc.reason,
        "uploaded_at": doc.created_at.isoformat(), "reviewed_at": doc.reviewed_at.isoformat() if doc.reviewed_at else None,
        "has_file": has_file(doc),
    }


def documents(pilgrim):
    """Checklist gabungan paket aktif + riwayat versi tiap jenis dokumen."""
    required = {}
    packages = {p.booking.departure.package_id: p.booking.departure.package for p in _participants(pilgrim).exclude(booking__status="CANCELED")}
    for package in packages.values():
        for req in effective_requirements(package):
            item = required.setdefault(req.kind, {"mandatory": False, "deadline_rule": req.deadline_rule})
            item["mandatory"] |= req.mandatory
            if req.deadline_rule == DocumentRequirementDeadline.BEFORE_READY:
                item["deadline_rule"] = req.deadline_rule
    history = {}
    for doc in PilgrimDocument.objects.filter(pilgrim=pilgrim).order_by("kind", "-version"):
        history.setdefault(doc.kind, []).append(_document_payload(doc))
    kinds = [kind for kind in PilgrimDocumentKind.values if kind in required or kind in history]
    return [{
        "kind": kind, "label": PilgrimDocumentKind(kind).label,
        "required": kind in required, "mandatory": required.get(kind, {}).get("mandatory", False),
        "deadline": DEADLINE_TEXT.get(required[kind]["deadline_rule"]) if kind in required else None,
        "latest": history.get(kind, [None])[0], "history": history.get(kind, []),
        "can_upload": not history.get(kind) or history[kind][0]["status"] != PilgrimDocumentStatus.APPROVED,
    } for kind in kinds]


def upload_for_access(*, user, access_id, kind, data, ext):
    with transaction.atomic(), scoped_access(user, access_id) as (access, pilgrim):
        tenant = Tenant.objects.get(pk=access.tenant_id)
        assert_environment_writable(tenant, pilgrim.environment)
        doc = add_uploaded_document(pilgrim_id=pilgrim.pk, kind=kind, data=data, ext=ext)
        log_event(action="pilgrim_documents.uploaded", tenant=tenant, actor=user, object_type="pilgrim_document", object_id=doc.pk, changes={"kind": kind, "version": doc.version, "source": "portal"})
        return _document_payload(doc)


# ----------------------------------------------------------------- profile --

PROFILE_FIELDS = ["phone", "email", "address", "emergency_contact_name", "emergency_contact_phone"]


def update_profile(*, user, access_id, data):
    """Jamaah hanya mengoreksi kontak; identitas (nama, NIK, paspor) tetap lewat travel."""
    unknown = set(data) - set(PROFILE_FIELDS)
    if unknown:
        raise ValidationError({key: "Field ini tidak dapat diubah dari portal." for key in unknown})
    with transaction.atomic(), scoped_access(user, access_id) as (access, pilgrim):
        tenant = Tenant.objects.get(pk=access.tenant_id)
        assert_environment_writable(tenant, pilgrim.environment)
        pilgrim = Pilgrim.objects.select_for_update().get(pk=pilgrim.pk)
        for field in PROFILE_FIELDS:
            if field not in data:
                continue
            value = str(data[field] or "").strip()
            if field in {"phone", "emergency_contact_phone"} and value:
                value = normalize_phone(value)
                if not 10 <= len(value) <= 16:
                    raise ValidationError({field: "Nomor telepon tidak valid."})
            if field == "email" and value and ("@" not in value or len(value) > 254):
                raise ValidationError({field: "Email tidak valid."})
            limit = {"address": 500, "emergency_contact_name": 160}.get(field, 254)
            setattr(pilgrim, field, value[:limit])
        pilgrim.save()
        log_event(action="pilgrims.updated", tenant=tenant, actor=user, object_type="pilgrim", object_id=pilgrim.pk, changes={"code": pilgrim.code, "fields": sorted(data), "source": "portal"})
        return _profile_payload(pilgrim)


# ------------------------------------------------------- pengumuman (POR-05) --


def announcement_payload(row):
    return {"id": str(row.pk), "title": row.title, "body": row.body, "published_at": row.published_at.isoformat() if row.published_at else None,
            "departure": {"id": str(row.departure_id), "code": row.departure.code} if row.departure_id else None}


def announcements_for(pilgrim, limit=10):
    from django.db.models import Q

    from modules.portal.models import Announcement

    now = timezone.now()
    departures = list(_participants(pilgrim).exclude(booking__status="CANCELED").values_list("booking__departure_id", flat=True))
    rows = (Announcement.objects.filter(environment=pilgrim.environment, published_at__isnull=False, published_at__lte=now)
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).filter(Q(departure__isnull=True) | Q(departure_id__in=departures))
            .select_related("departure").order_by("-published_at")[:limit])
    return [announcement_payload(r) for r in rows]


# ------------------------------------------- permintaan perubahan identitas (POR-06) --
IDENTITY_FIELDS = ["name", "gender", "birth_date", "birth_place", "nationality", "identity_number", "passport_number", "passport_name",
                   "passport_issued_at", "passport_expires_at", "passport_place_of_issue"]
FIELD_LABELS = {"name": "Nama sesuai dokumen", "gender": "Jenis kelamin", "birth_date": "Tanggal lahir", "birth_place": "Tempat lahir", "nationality": "Kewarganegaraan",
                "identity_number": "NIK", "passport_number": "Nomor paspor", "passport_name": "Nama di paspor", "passport_issued_at": "Tanggal terbit paspor",
                "passport_expires_at": "Paspor berlaku hingga", "passport_place_of_issue": "Kantor penerbit paspor"}
SECRET_FIELDS = {"identity_number", "passport_number"}


def change_request_payload(row):
    return {"id": str(row.pk), "status": row.status, "status_label": row.get_status_display(), "fields": row.fields,
            "changes": [{"field": f, "label": FIELD_LABELS.get(f, f), "value": row.preview_json.get(f, "")} for f in row.fields],
            "reason": row.reason, "decision_note": row.decision_note, "created_at": row.created_at.isoformat(),
            "decided_at": row.decided_at.isoformat() if row.decided_at else None}


def _validated_identity(pilgrim, data):
    import json

    from modules.pilgrims.crypto import mask_last4
    from modules.pilgrims.serializers import PilgrimWriteSerializer

    unknown = set(data) - set(IDENTITY_FIELDS)
    if unknown:
        raise ValidationError({key: "Field ini tidak termasuk data identitas." for key in unknown})
    if not data:
        raise ValidationError({"changes": "Isi minimal satu data yang ingin dikoreksi."})
    serializer = PilgrimWriteSerializer(pilgrim, data=data, partial=True)
    serializer.is_valid(raise_exception=True)
    clean = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in serializer.validated_data.items()}
    preview = {k: (mask_last4(str(v)) if k in SECRET_FIELDS else v) for k, v in clean.items()}
    return clean, preview, json.dumps(clean)


def submit_change_request(*, user, access_id, data, reason):
    from modules.pilgrims.crypto import encrypt_pii
    from modules.portal.models import ProfileChangeRequest

    changes = data if isinstance(data, dict) else {}
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Jelaskan alasan koreksi (mis. salah ketik nama sesuai paspor)."})
    with transaction.atomic(), scoped_access(user, access_id) as (access, pilgrim):
        tenant = Tenant.objects.get(pk=access.tenant_id)
        assert_environment_writable(tenant, pilgrim.environment)
        pilgrim = Pilgrim.objects.select_for_update().get(pk=pilgrim.pk)
        if ProfileChangeRequest.objects.filter(pilgrim=pilgrim, status="PENDING").exists():
            raise ValidationError({"changes": "Masih ada permintaan koreksi yang menunggu verifikasi travel."})
        clean, preview, raw = _validated_identity(pilgrim, changes)
        row = ProfileChangeRequest.objects.create(
            tenant_id=pilgrim.tenant_id, environment=pilgrim.environment, pilgrim=pilgrim, requested_by=user,
            fields=sorted(clean), payload_encrypted=encrypt_pii(raw), preview_json=preview, reason=str(reason).strip()[:500],
        )
        log_event(action="pilgrims.change_requested", tenant=tenant, actor=user, object_type="pilgrim", object_id=pilgrim.pk, changes={"fields": row.fields, "source": "portal"})
        return change_request_payload(row)


@transaction.atomic
def decide_change_request(*, request_id, actor, approve, note="", request=None):
    import json

    from modules.pilgrims.crypto import decrypt_pii
    from modules.pilgrims.serializers import PilgrimWriteSerializer
    from modules.pilgrims.views import _apply_identity, _mark_duplicate
    from modules.portal.models import ProfileChangeRequest

    row = ProfileChangeRequest.objects.select_for_update().select_related("pilgrim").get(pk=request_id)
    if row.status != "PENDING":
        raise ValidationError({"status": "Permintaan ini sudah diputuskan."})
    if not approve and not (note or "").strip():
        raise ValidationError({"note": "Alasan penolakan wajib diisi agar jamaah tahu yang perlu diperbaiki."})
    pilgrim = Pilgrim.objects.select_for_update().get(pk=row.pilgrim_id)
    assert_environment_writable(pilgrim.tenant, pilgrim.environment)
    if approve:
        serializer = PilgrimWriteSerializer(pilgrim, data=json.loads(decrypt_pii(row.payload_encrypted)), partial=True)
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)
        _apply_identity(pilgrim, validated)
        for field, value in validated.items():
            setattr(pilgrim, field, value)
        _mark_duplicate(pilgrim)
        pilgrim.save()
    row.status, row.decided_by, row.decided_at, row.decision_note = ("APPROVED" if approve else "REJECTED"), actor, timezone.now(), (note or "").strip()[:500]
    row.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    log_event(action=f"pilgrims.change_{'approved' if approve else 'rejected'}", request=request, actor=actor, object_type="pilgrim", object_id=pilgrim.pk, changes={"fields": row.fields})
    return row
