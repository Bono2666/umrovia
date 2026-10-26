"""Layanan checklist operasional & manifest (Spec §5.2, §6.5, §7.6, §8.3;
PRD MOD-08/MOD-12, OPS-02/OPS-03, UAT-14).

Checklist (gerbang transisi):
- `effective_requirements(package)` → checklist efektif: requirement global
  (package null) ditimpa per `kind` oleh requirement spesifik paket.
- `checklist_gaps(departure, stage)` → daftar kekurangan dokumen WAJIB untuk
  satu keberangkatan pada `stage` (`before_ready`/`before_departure`):
  setiap peserta booking aktif (bukan CANCELED/EXPIRED) wajib punya dokumen
  jenis wajib ber-status APPROVED pada **versi terakhir** tiap jenis.
  Tanpa requirement berlaku → daftar kosong (gerbang longgar sampai checklist
  dikonfigurasi — mengisi hook S08 `checklist_complete` / S09
  `documents_complete` yang semula selalu True).
- `checklist_complete(departure)` → (lengkap, alasan) untuk gerbang READY
  (§6.5; pengecualian resmi ditangani pemanggil via `checklist_exception`).
- `booking_document_gaps(booking)` → kekurangan pada peserta satu booking
  saja (gerbang booking → READY_TO_DEPART).

Manifest:
- `manifest_rows(...)` → daftar jamaah dari booking aktif keberangkatan
  (UAT-14: hanya peserta departure itu), field ter-mask; `pii=True` menambah
  NIK/paspor hasil dekripsi + kebutuhan khusus (§10.1) — hanya untuk jalur
  ekspor berizin & diaudit (OPS03).
- `publish_manifest(...)` → snapshot JSON roster + versi bernomor unik +
  checksum sha256 (append-only; revisi = versi baru).
- `export_csv(...)` → teks CSV (BOM UTF-8 untuk Excel) dengan filter
  MOD-12 (q/status peserta/status dokumen/status charge).
"""
import csv
import hashlib
import io
import json

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone
from rest_framework.exceptions import APIException

from modules.booking.models import BookingParticipant, BookingStatus
from modules.manifest.models import (
    DocumentRequirement,
    DocumentRequirementDeadline,
    ManifestVersion,
)
from modules.payments.models import InvoiceLine, PaymentAllocation
from modules.pilgrims.crypto import PIIDecryptionError, decrypt_pii
from modules.pilgrims.models import (
    Pilgrim,
    PilgrimDocument,
    PilgrimDocumentKind,
    PilgrimDocumentStatus,
)
from modules.tenants.context import get_current_tenant
from modules.tenants.environment import resolve_active_environment

# Booking yang tidak lagi memegang kursi/kewajiban → tidak masuk checklist
# maupun manifest (MOD-07 terminal negatif).
INACTIVE_BOOKING_STATUSES = (BookingStatus.CANCELED, BookingStatus.EXPIRED)


def effective_requirements(package) -> list[DocumentRequirement]:
    """Checklist dalam satu environment; paket menimpa global per jenis."""
    environment = package.environment if package is not None else resolve_active_environment(get_current_tenant())
    requirements = DocumentRequirement.objects.filter(environment=environment)
    by_kind = {
        r.kind: r
        for r in requirements.filter(package__isnull=True)
    }
    if package is not None:
        for row in requirements.filter(package=package):
            by_kind[row.kind] = row
    return sorted(by_kind.values(), key=lambda r: r.kind)


def active_participants(departure):
    """Peserta booking aktif pada keberangkatan, urut booking (manifest/checklist)."""
    return (
        BookingParticipant.objects.filter(booking__departure=departure)
        .exclude(booking__status__in=INACTIVE_BOOKING_STATUSES)
        .select_related("booking", "pilgrim")
        .order_by("booking__code", "created_at")
    )


def latest_doc_statuses(pilgrim_ids) -> dict:
    """Status dokumen VERSI TERAKHIR per (jamaah, jenis) — satu query.

    `PilgrimDocument` terurut `kind, -version` (Meta model) → kemunculan
    pertama per pasangan = versi tertinggi.
    """
    statuses: dict = {pid: {} for pid in pilgrim_ids}
    seen: set = set()
    docs = PilgrimDocument.objects.filter(pilgrim_id__in=pilgrim_ids).order_by(
        "pilgrim_id", "kind", "-version"
    )
    for doc in docs:
        key = (doc.pilgrim_id, doc.kind)
        if key in seen:
            continue
        seen.add(key)
        statuses[doc.pilgrim_id][doc.kind] = doc.status
    return statuses


def gap_message(gaps: list[str]) -> str:
    """Alasan manusiawi dari daftar kekurangan (maks 5 item + sisa)."""
    shown = "; ".join(gaps[:5])
    if len(gaps) > 5:
        shown += f"; … (+{len(gaps) - 5} lain)"
    return f"Dokumen wajib belum lengkap ({len(gaps)}): {shown}"


def checklist_gaps(departure, *, stage: str) -> list[str]:
    """Kekurangan dokumen wajib pada `stage` untuk seluruh peserta aktif."""
    reqs = [
        r
        for r in effective_requirements(departure.package)
        if r.mandatory and r.deadline_rule == stage
    ]
    if not reqs:
        return []
    participants = list(active_participants(departure))
    if not participants:
        return []
    statuses = latest_doc_statuses([p.pilgrim_id for p in participants])
    gaps: list[str] = []
    for row in participants:
        latest = statuses.get(row.pilgrim_id, {})
        for req in reqs:
            status = latest.get(req.kind)
            if status == PilgrimDocumentStatus.APPROVED:
                continue
            label = PilgrimDocumentKind(req.kind).label
            if status is None:
                state = "belum diunggah"
            else:
                state = f"status {PilgrimDocumentStatus(status).label.lower()}"
            gaps.append(f"{row.pilgrim.name} — {label} ({state})")
    return gaps


def checklist_complete(departure) -> tuple[bool, str]:
    """Gerbang READY keberangkatan (§6.5, dipakai `departures.services`).

    Pengecualian resmi (*approved exception*) ditangani pemanggil: bila
    `checklist_exception` + alasan disampaikan pada transisi, gate dilewati
    dengan jejak `departure_events` + audit.
    """
    gaps = checklist_gaps(departure, stage=DocumentRequirementDeadline.BEFORE_READY)
    if gaps:
        return False, gap_message(gaps)
    return True, ""


def booking_document_gaps(booking) -> list[str]:
    """Kekurangan dokumen peserta SATU booking (gerbang READY_TO_DEPART)."""
    reqs = [
        r
        for r in effective_requirements(booking.departure.package)
        if r.mandatory and r.deadline_rule == DocumentRequirementDeadline.BEFORE_READY
    ]
    if not reqs:
        return []
    participants = list(BookingParticipant.objects.filter(booking=booking).select_related("pilgrim"))
    if not participants:
        return []
    statuses = latest_doc_statuses([p.pilgrim_id for p in participants])
    gaps: list[str] = []
    for row in participants:
        latest = statuses.get(row.pilgrim_id, {})
        for req in reqs:
            status = latest.get(req.kind)
            if status == PilgrimDocumentStatus.APPROVED:
                continue
            label = PilgrimDocumentKind(req.kind).label
            state = "belum diunggah" if status is None else (
                f"status {PilgrimDocumentStatus(status).label.lower()}"
            )
            gaps.append(f"{row.pilgrim.name} — {label} ({state})")
    return gaps


def booking_documents_complete(booking) -> tuple[bool, str]:
    """Gerbang booking → READY_TO_DEPART (mengisi hook S09 `documents_complete`).

    Tanpa pengecualian eksplisit di level booking — atur lewat requirement
    (uncheck `mandatory`) bila memang tidak berlaku.
    """
    gaps = booking_document_gaps(booking)
    if gaps:
        return False, gap_message(gaps)
    return True, ""


# ------------------------------------------------------------------ manifest --


CONFIRMED_LIKE = {"CONFIRMED", "READY", "DEPARTED", "COMPLETED"}
PAYMENT_FILTERS = {"", "paid", "partial", "unpaid"}


def payment_by_participant(participants) -> dict:
    """Tagihan (baris invoice aktif atau snapshot harga) dan alokasi VERIFIED per peserta — 2 query."""
    ids = [p.pk for p in participants]
    lines = dict(
        InvoiceLine.objects.filter(participant_id__in=ids).exclude(invoice__status="VOIDED").values_list("participant_id", "amount_idr")
    )
    paid = dict(
        PaymentAllocation.objects.filter(participant_id__in=ids, payment__status="VERIFIED")
        .values("participant_id").annotate(total=Sum("amount_idr")).values_list("participant_id", "total")
    )
    result = {}
    for p in participants:
        amount = lines.get(p.pk, int(p.pricing_snapshot_json.get("unit_price_idr") or 0))
        received = paid.get(p.pk, 0) or 0
        status = "paid" if amount and received >= amount else "partial" if received else "unpaid"
        result[p.pk] = {"amount_idr": amount, "paid_idr": received, "balance_idr": max(amount - received, 0), "payment_status": status}
    return result


def manifest_rows(
    departure,
    *,
    pii: bool = False,
    q: str = "",
    document: str = "",
    participant_status: str = "",
    charge_state: str = "",
    payment: str = "",
    booking: str = "",
) -> list[dict]:
    """Roster manifest peserta aktif `departure` (UAT-14) dengan filter MOD-12.

    Field dasar selalu masked (§10.1). `pii=True` hanya dipanggil dari jalur
    ekspor yang sudah lolos permission `manifest.export_pii` + audit.
    """
    requirements = effective_requirements(departure.package)
    required_kinds = [r.kind for r in requirements if r.mandatory]
    rows = list(active_participants(departure))
    statuses = latest_doc_statuses([r.pilgrim_id for r in rows])
    payments = payment_by_participant(rows)

    out: list[dict] = []
    for row in rows:
        pilgrim: Pilgrim = row.pilgrim
        latest = statuses.get(pilgrim.pk, {})
        missing = [
            k for k in required_kinds if latest.get(k) != PilgrimDocumentStatus.APPROVED
        ]
        entry = {
            "booking_id": str(row.booking_id),
            "booking_code": row.booking.code,
            "participant_id": str(row.id),
            "participant_status": row.participant_status,
            "saas_charge_state": row.saas_charge_state,
            "pilgrim_id": str(pilgrim.pk),
            "pilgrim_code": pilgrim.code,
            "name": pilgrim.name,
            "gender": pilgrim.gender,
            "birth_date": pilgrim.birth_date.isoformat() if pilgrim.birth_date else None,
            "phone": pilgrim.phone,
            "identity_masked": pilgrim.identity_masked,
            "passport_masked": pilgrim.passport_masked,
            "docs": {k: latest.get(k) for k in sorted(set(latest))},
            "docs_required": required_kinds,
            "docs_missing": missing,
            "docs_complete": not missing,
            "room_type": row.pricing_snapshot_json.get("room_type") or "",
            "dp_received": row.dp_eligible_at is not None,
            **payments[row.pk],
        }
        if pii:
            try:
                entry["identity_number"] = decrypt_pii(pilgrim.identity_encrypted)
                entry["passport_number"] = decrypt_pii(pilgrim.passport_encrypted)
            except PIIDecryptionError as exc:  # key hilang → gagal jelas (§10.1)
                raise APIException("Dekripsi PII gagal — periksa PII_ENCRYPTION_KEY.") from exc
            entry["address"] = pilgrim.address
            entry["special_needs"] = pilgrim.special_needs
        # filter MOD-12 (dihitung setelah entry dibuat)
        if document == "complete" and missing:
            continue
        if document == "incomplete" and not missing:
            continue
        if participant_status and row.participant_status != participant_status:
            continue
        if charge_state and row.saas_charge_state != charge_state:
            continue
        if payment and entry["payment_status"] != payment:
            continue
        if booking and str(row.booking_id) != booking:
            continue
        if q:
            needle = q.lower()
            hay = " ".join(
                [row.booking.code, pilgrim.code, pilgrim.name, pilgrim.phone or ""]
            ).lower()
            if needle not in hay:
                continue
        out.append(entry)
    return out


def readiness(departure, rows=None) -> dict:
    """Ringkasan kesiapan (OPS-06): dokumen, pembayaran, konfirmasi dan gerbang READY."""
    rows = manifest_rows(departure) if rows is None else rows
    gaps = checklist_gaps(departure, stage="before_ready")

    def count(predicate):
        return sum(1 for row in rows if predicate(row))

    return {
        "participants": len(rows),
        "docs_complete": count(lambda r: r["docs_complete"]),
        "dp_received": count(lambda r: r["dp_received"]),
        "fully_paid": count(lambda r: r["payment_status"] == "paid"),
        "confirmed": count(lambda r: r["participant_status"] in CONFIRMED_LIKE),
        "pending_charge": count(lambda r: r["saas_charge_state"] == "pending_charge"),
        "outstanding_idr": sum(r["balance_idr"] for r in rows),
        "seat_capacity": departure.seat_capacity,
        "seats_taken": departure.seats_taken,
        "available_seats": departure.available_seats,
        "checklist_ready": not gaps,
        "gap_count": len(gaps),
    }


def publish_manifest(*, departure, actor=None) -> ManifestVersion:
    """Snapshot roster → file JSON + `ManifestVersion` bernomor unik (§7.6).

    Baris departure di-lock → dua penerbit serentak diserialisasi, versi
    nomor urut tanpa tabrakan (UNIQUE(departure, version_no)).
    """
    with transaction.atomic():
        dep = type(departure).objects.select_for_update().get(pk=departure.pk)
        last = (
            ManifestVersion.objects.filter(departure=dep).aggregate(m=Max("version_no"))["m"]
            or 0
        )
        version_no = last + 1
        rows = manifest_rows(dep, pii=False)
        snapshot = {
            "departure": {
                "id": str(dep.pk),
                "code": dep.code,
                "package_code": dep.package.code,
                "package_name": dep.package.name,
                "start_at": dep.start_at.isoformat(),
                "city_of_origin": dep.city_of_origin,
                "route": dep.route,
                "seat_capacity": dep.seat_capacity,
                "seats_taken": dep.seats_taken,
                "status": dep.status,
            },
            "version_no": version_no,
            "published_at": timezone.now().isoformat(),
            "row_count": len(rows),
            "rows": rows,
        }
        raw = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True).encode()
        checksum = hashlib.sha256(raw).hexdigest()
        key = default_storage.save(
            f"manifests/{dep.tenant_id}/{dep.environment}/{dep.code}/v{version_no}.json",
            ContentFile(raw),
        )
        version = ManifestVersion.objects.create(
            tenant=dep.tenant,
            environment=dep.environment,
            departure=dep,
            version_no=version_no,
            published_by=actor if getattr(actor, "is_authenticated", False) else None,
            snapshot_object_key=key,
            checksum=checksum,
        )
    return version


CSV_BASE_HEADERS = [
    "Kode booking",
    "Kode jamaah",
    "Nama",
    "Jenis kelamin",
    "Tanggal lahir",
    "Telepon",
    "NIK (masked)",
    "Paspor (masked)",
    "Status peserta",
    "Status charge SaaS",
    "Dokumen wajib lengkap",
    "Kekurangan dokumen",
]
CSV_PII_HEADERS = ["NIK", "Nomor paspor", "Alamat", "Kebutuhan khusus"]


def export_csv(departure, *, pii: bool = False, **filters) -> tuple[str, int]:
    """CSV manifest (BOM UTF-8) — hanya peserta `departure` (UAT-14).

    Mengembalikan (teks, jumlah baris) agar ekspor tercatat presisi di audit.
    """
    rows = manifest_rows(departure, pii=pii, **filters)
    headers = CSV_BASE_HEADERS + (CSV_PII_HEADERS if pii else [])
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    for row in rows:
        line = [
            row["booking_code"],
            row["pilgrim_code"],
            row["name"],
            row["gender"],
            row["birth_date"] or "",
            row["phone"],
            row["identity_masked"],
            row["passport_masked"],
            row["participant_status"],
            row["saas_charge_state"],
            "ya" if row["docs_complete"] else "tidak",
            "; ".join(row["docs_missing"]),
        ]
        if pii:
            line += [
                row.get("identity_number", ""),
                row.get("passport_number", ""),
                row.get("address", ""),
                row.get("special_needs", ""),
            ]
        writer.writerow(line)
    return "\ufeff" + buffer.getvalue(), len(rows)  # BOM agar Excel membaca UTF-8


def export_filename(departure) -> str:
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    prefix = "DEMO-manifest" if departure.environment == "demo" else "manifest"  # §7.2
    return f"{prefix}-{departure.code}-{stamp}.csv"
