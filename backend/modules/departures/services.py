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
dari DRAFT/OPEN/READY. `READY` dijaga kelengkapan checklist — hook
`checklist_complete` saat ini selalu True, diisi riil pada S10 (modul
manifest/checklist) sesuai catatan "approved exception" §6.5.
"""
from django.core.exceptions import ValidationError
from django.db.models import F

from modules.departures.models import Departure, DepartureEvent, DepartureStatus

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

    Hook untuk modul checklist S10 — selama checklist belum ada dianggap
    lengkap (tidak ada yang bisa kurang). Mengembalikan (lengkap, alasan).
    """
    return True, ""


def transition_departure(*, departure: Departure, target: str, actor=None, reason: str = "") -> Departure:
    """Transisi status dengan guard state machine + tulis `departure_events`.

    `CANCELED` mewajibkan `reason` (MOD-06: pembatalan dengan approval —
  approval diwakili permission `departures.manage` + alasan tercatat).
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
            raise ValidationError({"checklist": why})

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
