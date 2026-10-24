"""Layanan domain keberangkatan: seat atomik (BR-002) + state machine (§6.5).

Seat (UAT-02, PRD BR-002):
- `reserve_seats(departure, n)` → UPDATE tunggal dengan guard WHERE
  (`seats_taken + n + seats_blocked <= seat_capacity`). Postgres mengunci
  baris selama UPDATE; dua transaksi serentak pada kursi terakhir
  diserialisasi → tepat satu sukses (rowcount 1), satu lagi 0.
  Invariant CHECK di schema adalah pengaman kedua.
- `release_seats(departure, n)` → decrement atomik ber-guard — tidak pernah
  di bawah 0 (untuk pembatalan booking, S09).

Transisi (§6.5): DRAFT → OPEN → READY → DEPARTED → COMPLETED atau CANCELED
dari DRAFT/OPEN/READY. Dua gerbang checklist (diisi S10 — modul `manifest`):
- `READY` dijaga `checklist_complete` (dokumen wajib `before_ready` milik
  seluruh peserta booking aktif harus APPROVED). *Approved exception* §6.5 =
  flag `checklist_exception` + wajib alasan pada transisi → gate dilewati
  dengan jejak `departure_events` + audit (OPS02: tanpa exception, READY
  dengan dokumen belum lengkap = ditolak).
- `DEPARTED` dijaga kekurangan requirement `before_departure` (strict —
  tanpa exception, sesuai §7.6 keberangkatan fisik).
"""
from django.core.exceptions import ValidationError
from django.db.models import F

from modules.departures.models import Departure, DepartureEvent, DepartureStatus
from modules.manifest.services import checklist_gaps, gap_message

# Graf transisi sah §6.5 (terminal: COMPLETED, CANCELED).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    DepartureStatus.DRAFT: {DepartureStatus.OPEN, DepartureStatus.CANCELED},
    DepartureStatus.OPEN: {DepartureStatus.READY, DepartureStatus.CANCELED},
    DepartureStatus.READY: {DepartureStatus.DEPARTED, DepartureStatus.CANCELED},
    DepartureStatus.DEPARTED: {DepartureStatus.COMPLETED},
    DepartureStatus.COMPLETED: set(),
    DepartureStatus.CANCELED: set(),
}


def checklist_complete(departure: Departure) -> tuple[bool, str]:
    """Gerbang READY (§6.5): kelengkapan checklist / approved exception.

    Diisi riil pada S10 lewat `modules.manifest` — menghitung dokumen wajib
    (`deadline_rule=before_ready`) milik setiap peserta booking aktif; tanpa
    requirement yang berlaku dianggap lengkap (tidak ada yang bisa kurang).
    Pengecualian resmi ditangani pemanggil via `checklist_exception`.
    """
    gaps = checklist_gaps(departure, stage="before_ready")
    if gaps:
        return False, gap_message(gaps)
    return True, ""


def transition_departure(
    *,
    departure: Departure,
    target: str,
    actor=None,
    reason: str = "",
    checklist_exception: bool = False,
) -> Departure:
    """Transisi status dengan guard state machine + tulis `departure_events`.

    `CANCELED` mewajibkan `reason` (MOD-06: pembatalan dengan approval —
  approval diwakili permission `departures.manage` + alasan tercatat).
    `checklist_exception` (§6.5 *approved exception*, OPS02) hanya berlaku
    untuk `READY` dan wajib menyertai `reason` — tercatat di
    `departure_events.reason` + audit perubahan.
    """
    current = departure.status
    if target not in {c for c, _ in DepartureStatus.choices}:
        raise ValidationError({"target": "Status tujuan tidak dikenal."})
    if target == current:
        raise ValidationError({"target": f"Status sudah {target}."})
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValidationError(
            {"target": f"Transisi {current} → {target} tidak diizinkan (kontrak §6.5)."}
        )
    if target == DepartureStatus.CANCELED and not (reason or "").strip():
        raise ValidationError({"reason": "Alasan pembatalan wajib diisi."})
    if target == DepartureStatus.OPEN and departure.seat_capacity < 1:
        raise ValidationError({"seat_capacity": "Pendaftaran hanya dibuka bila kapasitas ≥ 1."})
    if target == DepartureStatus.READY:
        complete, why = checklist_complete(departure)
        if not complete:
            if not checklist_exception:
                raise ValidationError({"checklist": why})
            if not (reason or "").strip():
                raise ValidationError(
                    {"reason": "Approved exception checklist wajib menyertai alasan."}
                )
    if target == DepartureStatus.DEPARTED:
        gaps = checklist_gaps(departure, stage="before_departure")
        if gaps:
            raise ValidationError({"checklist": gap_message(gaps)})

    departure.status = target
    departure.save(update_fields=["status", "updated_at"])
    DepartureEvent.objects.create(
        tenant=departure.tenant,
        environment=departure.environment,
        departure=departure,
        prior_status=current,
        next_status=target,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        reason=(reason or "").strip(),
    )
    return departure


def reserve_seats(departure_id, seats: int) -> bool:
    """Amankan `seats` kursi secara atomik. True bila berhasil, False bila penuh.

    Satu statement UPDATE dengan guard WHERE → baris terkunci; pemesan
    serentak pada kursi terakhir menghasilkan tepat satu sukses (UAT-02).
    Dipanggil dalam transaksi booking (S09) — fungsi ini sendiri aman
    dipanggil lintas transaksi.
    """
    if seats < 1:
        raise ValidationError({"seats": "Jumlah kursi harus ≥ 1."})
    updated = (
        Departure.objects.filter(pk=departure_id)
        .filter(seat_capacity__gte=F("seats_blocked") + F("seats_taken") + seats)
        .update(seats_taken=F("seats_taken") + seats)
    )
    return updated == 1


def release_seats(departure_id, seats: int) -> bool:
    """Lepas `seats` kursi (pembatalan booking, S09). Guard: tak pernah < 0."""
    if seats < 1:
        raise ValidationError({"seats": "Jumlah kursi harus ≥ 1."})
    updated = (
        Departure.objects.filter(pk=departure_id)
        .filter(seats_taken__gte=seats)
        .update(seats_taken=F("seats_taken") - seats)
    )
    return updated == 1
