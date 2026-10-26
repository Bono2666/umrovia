"""Layanan domain booking: tautan peserta ↔ keberangkatan (MOD-07, UAT-03),
kursi atomik (BR-002/UAT-02), state machine header MOD-07 + peserta §6.2,
snapshot harga (UAT-04) dan kuota trial (POL-08/§7.1.5).

Alur (S09 "Booking end-to-end"):
- **create** → `DRAFT` (BELUM menahan kursi) dengan peserta unik ≥ 1 dan baris
  harga snapshot. Guard: keberangkatan harus `OPEN`, belum lewat deadline,
  jamaah satu environment, satu jamaah maksimal SATU booking aktif per
  keberangkatan (MOD-07) — divalidasi di bawah `SELECT FOR UPDATE` baris
  departure sehingga dua pembuat serentak diserialisasi (bebas race).
- **DRAFT → RESERVED** = `reserve_seats(n)` atomik (n = jumlah peserta) —
  dua staf serentak memperebutkan kursi terakhir → tepat satu menang
  (UAT-02 di level booking). RESERVED juga dijaga departure masih OPEN.
- **CANCELED** (alasan wajib) dari status penahan kursi → `release_seats(n)`;
  **EXPIRED** terminal terkontrol: hanya setelah pendaftaran ditutup
  (deadline lewat/keberangkatan READY+); dari RESERVED melepas kursi.
- **Peserta** di-advance sinkron dengan header (§6.2 ↔ MOD-07): RESERVED →
  REGISTERED, CONFIRMED → CONFIRMED, READY_TO_DEPART → READY, DEPARTED →
  DEPARTED, COMPLETED → COMPLETED, CANCELED/EXPIRED → CANCELED. S11 memakai
  tahap AWAITING_DP → DP_VERIFIED_PENDING_CHARGE; konfirmasi produksi
  menunggu charge S12/S13, sedangkan simulasi demo tidak menyentuh ledger.
- **Kuota trial (POL-08):** selama trial berjalan, pembuatan booking
  mengonsumsi `TenantTrial.dummy_count` — SATU UNIT = SATU PESERTA
  (booking-jamaah; §16 "20 dummy jamaah"). Increment SEBELUM create dan
  dalam transaksi yang sama (rollback bila create gagal); tidak pernah
  dikurangi (TR03) — mengikuti pola `create_demo_booking` (S04); record
  `DemoBooking` digantikan booking nyata berbasis environment (docstring).
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from modules.booking.models import (
    Booking,
    BookingParticipant,
    BookingPriceLine,
    BookingStatus,
    ParticipantStatus,
    SaasChargeState,
    generate_booking_code,
)
from modules.catalog.models import TravelPackage
from modules.departures.models import Departure, DepartureStatus
from modules.departures.services import release_seats, reserve_seats
from modules.manifest.services import booking_documents_complete
from modules.pilgrims.models import Pilgrim
from modules.trial.exceptions import TrialQuotaExceeded
from modules.trial.models import TenantTrial

# Graf transisi header (PRD MOD-07). Terminal: COMPLETED, CANCELED, EXPIRED.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    BookingStatus.DRAFT: {
        BookingStatus.RESERVED,
        BookingStatus.CANCELED,
        BookingStatus.EXPIRED,
    },
    BookingStatus.RESERVED: {
        BookingStatus.CONFIRMED,
        BookingStatus.CANCELED,
        BookingStatus.EXPIRED,
    },
    BookingStatus.CONFIRMED: {
        BookingStatus.DOCUMENT_PROCESS,
        BookingStatus.CANCELED,
    },
    BookingStatus.DOCUMENT_PROCESS: {
        BookingStatus.READY_TO_DEPART,
        BookingStatus.CANCELED,
    },
    BookingStatus.READY_TO_DEPART: {BookingStatus.DEPARTED, BookingStatus.CANCELED},
    BookingStatus.DEPARTED: {BookingStatus.COMPLETED},
    BookingStatus.COMPLETED: set(),
    BookingStatus.CANCELED: set(),
    BookingStatus.EXPIRED: set(),
}

# Graph peserta (Spec §6.2) — dipakai `advance_participant` (layanan
# pembayaran S11/S12) dan guard `CANCELED`/`REVIEW_REQUIRED`.
PARTICIPANT_TRANSITIONS: dict[str, set[str]] = {
    ParticipantStatus.DRAFT: {ParticipantStatus.REGISTERED, ParticipantStatus.CANCELED},
    ParticipantStatus.REGISTERED: {
        ParticipantStatus.AWAITING_DP,
        ParticipantStatus.CANCELED,
        ParticipantStatus.REVIEW_REQUIRED,
    },
    ParticipantStatus.AWAITING_DP: {
        ParticipantStatus.DP_VERIFIED_PENDING_CHARGE,
        ParticipantStatus.CANCELED,
        ParticipantStatus.REVIEW_REQUIRED,
    },
    ParticipantStatus.DP_VERIFIED_PENDING_CHARGE: {
        ParticipantStatus.CONFIRMED,
        ParticipantStatus.CANCELED,
        ParticipantStatus.REVIEW_REQUIRED,
    },
    ParticipantStatus.CONFIRMED: {
        ParticipantStatus.READY,
        ParticipantStatus.CANCELED,
        ParticipantStatus.REVIEW_REQUIRED,
    },
    ParticipantStatus.READY: {
        ParticipantStatus.DEPARTED,
        ParticipantStatus.CANCELED,
        ParticipantStatus.REVIEW_REQUIRED,
    },
    ParticipantStatus.DEPARTED: {ParticipantStatus.COMPLETED},
    ParticipantStatus.COMPLETED: set(),
    ParticipantStatus.CANCELED: set(),
    ParticipantStatus.REVIEW_REQUIRED: {
        ParticipantStatus.REGISTERED,
        ParticipantStatus.CANCELED,
    },
}

# Status yang menahan kursi pada keberangkatan (mirror legacy
# SEAT_CONSUMING_STATUSES): kursi di-reserve saat masuk status ini.
SEAT_CONSUMING_STATUSES = {
    BookingStatus.RESERVED,
    BookingStatus.CONFIRMED,
    BookingStatus.DOCUMENT_PROCESS,
    BookingStatus.READY_TO_DEPART,
}

# Target status peserta mengikuti transisi header; None = tanpa perubahan.
HEADER_PARTICIPANT_TARGET: dict[str, str | None] = {
    BookingStatus.RESERVED: ParticipantStatus.REGISTERED,
    BookingStatus.CONFIRMED: ParticipantStatus.CONFIRMED,
    BookingStatus.DOCUMENT_PROCESS: None,
    BookingStatus.READY_TO_DEPART: ParticipantStatus.READY,
    BookingStatus.DEPARTED: ParticipantStatus.DEPARTED,
    BookingStatus.COMPLETED: ParticipantStatus.COMPLETED,
    BookingStatus.CANCELED: ParticipantStatus.CANCELED,
    BookingStatus.EXPIRED: ParticipantStatus.CANCELED,
}

# Tangga advance peserta di jalur header (status peserta saat ini → target).
# Tahap DP dijalankan layanan pembayaran; tidak ada shortcut REGISTERED→CONFIRMED.
HEADER_PARTICIPANT_LADDER: dict[str, str] = {
    ParticipantStatus.DRAFT: ParticipantStatus.REGISTERED,
    ParticipantStatus.CONFIRMED: ParticipantStatus.READY,
    ParticipantStatus.READY: ParticipantStatus.DEPARTED,
    ParticipantStatus.DEPARTED: ParticipantStatus.COMPLETED,
}


def dp_confirmed(booking: Booking) -> tuple[bool, str]:
    """Gerbang CONFIRMED (MOD-07: "Reserved hanya dikonfirmasi sesuai aturan
    DP/pelunasan yang dapat dikonfigurasi").

    S11 menuntut DP eligible setiap peserta; produksi juga menunggu charge
    SaaS S12/S13. Simulasi demo dapat dikonfirmasi tanpa ledger produksi.
    """
    from modules.payments.services import booking_dp_confirmed

    return booking_dp_confirmed(booking)


def documents_complete(booking: Booking) -> tuple[bool, str]:
    """Gerbang READY_TO_DEPART — kelengkapan dokumen peserta (§6.5 pola
    "approved exception" level keberangkatan).

    Diisi riil pada S10 lewat `modules.manifest`: setiap peserta booking
    wajib punya dokumen jenis wajib (`before_ready`) ber-APPROVED pada
    versi terakhir. Tanpa requirement yang berlaku → lengkap (tidak ada
    yang bisa kurang). Level booking sengaja TANPA exception — bila aturan
    tidak berlaku, uncheck `mandatory` pada DocumentRequirement.
    """
    return booking_documents_complete(booking)


def registration_closed(departure: Departure) -> bool:
    """Pendaftaran tertutup (MOD-06 turunan CLOSED: deadline lewat / READY+)."""
    if departure.status in (
        DepartureStatus.READY,
        DepartureStatus.DEPARTED,
        DepartureStatus.COMPLETED,
        DepartureStatus.CANCELED,
    ):
        return True
    if departure.registration_deadline and timezone.localdate() > departure.registration_deadline:
        return True
    if departure.start_at <= timezone.now():
        return True
    return False


def _guard_departure_bookable(departure: Departure, *, environment: str) -> None:
    """Guard pembuatan/ubah draft booking: keberangkatan menerima pendaftaran."""
    if departure.environment != environment:
        raise ValidationError(
            {"departure": f"Keberangkatan harus berasal dari environment aktif '{environment}'."}
        )
    if departure.status != DepartureStatus.OPEN:
        raise ValidationError(
            {"departure": "Pendaftaran hanya diterima pada keberangkatan OPEN (MOD-06)."}
        )
    if departure.start_at <= timezone.now():
        raise ValidationError({"departure": "Keberangkatan sudah berangkat — pendaftaran ditutup."})
    if departure.registration_deadline and timezone.localdate() > departure.registration_deadline:
        raise ValidationError({"departure": "Batas pendaftaran sudah lewat (§10.1)."})


def _resolve_pilgrims(*, environment: str, pilgrim_ids) -> list[Pilgrim]:
    """Validasi jamaah: ≥ 1, unik dalam booking, ada & satu environment."""
    if not pilgrim_ids:
        raise ValidationError({"participants": "Minimal satu peserta (UAT-03)."})
    if len(set(pilgrim_ids)) != len(pilgrim_ids):
        raise ValidationError({"participants": "Jamaah yang sama tidak boleh dua kali dalam satu booking."})
    pilgrims = list(Pilgrim.objects.filter(pk__in=pilgrim_ids, environment=environment))
    if len(pilgrims) != len(set(pilgrim_ids)):
        raise ValidationError(
            {"participants": "Ada jamaah yang tidak ditemukan atau lintas-environment."}
        )
    return pilgrims


def _check_duplicate_active(
    *,
    departure: Departure,
    pilgrim_ids,
    allow_duplicate: bool,
    exclude_booking: Booking | None = None,
) -> None:
    """Satu jamaah maksimal satu booking AKTIF per keberangkatan (MOD-07) —
    kecuali `allow_duplicate` (override eksplisit). Dipanggil setelah baris
    departure terkunci (SELECT FOR UPDATE) → diserialisasi antar-pembuat."""
    if allow_duplicate:
        return
    qs = (
        BookingParticipant.objects.filter(pilgrim_id__in=pilgrim_ids, booking__departure=departure)
        .exclude(booking__status__in=[BookingStatus.CANCELED, BookingStatus.EXPIRED])
        .select_related("booking", "pilgrim")
    )
    if exclude_booking is not None:
        qs = qs.exclude(booking=exclude_booking)
    taken = list(qs)
    if taken:
        names = ", ".join(sorted({t.pilgrim.name for t in taken}))
        raise ValidationError(
            {
                "participants": (
                    f"Jamaah sudah memiliki booking aktif pada keberangkatan ini: {names} "
                    "(MOD-07). Gunakan allow_duplicate bila memang disengaja."
                )
            }
        )


def _consume_trial_quota(tenant, units: int) -> None:
    """Kuota booking-jamaah dummy trial (POL-08: 20 kumulatif; §7.1.5).

    Satu unit = satu peserta. Increment SEBELUM create dalam transaksi yang
    sama — bila create gagal, rollback mengembalikan counter; delete tidak
    pernah mengurangi (TR03). Tenant non-trial lewat tanpa cek.
    """
    if units < 1:
        return
    trial = TenantTrial.objects.select_for_update().filter(tenant=tenant).first()
    if trial is None or not trial.is_running:
        return
    if trial.dummy_count + units > trial.dummy_booking_limit:
        raise TrialQuotaExceeded(
            f"Kuota {trial.dummy_booking_limit} booking-jamaah dummy trial terpakai semua."
        )
    trial.dummy_count += units
    trial.save(update_fields=["dummy_count", "updated_at"])


def _snapshot_unit_price(departure: Departure, room_type: str = "") -> dict:
    pkg = departure.package
    prices = {row.room_type: row.price_idr for row in pkg.room_prices.all()}
    if prices and room_type not in prices:
        raise ValidationError({"room_types": "Pilih tipe kamar yang tersedia untuk setiap jamaah."})
    if not prices and room_type:
        raise ValidationError({"room_types": "Paket ini belum memiliki harga tipe kamar tersebut."})
    return {
        "package_id": str(pkg.id),
        "package_code": pkg.code,
        "package_name": pkg.name,
        "room_type": room_type,
        "unit_price_idr": int(prices[room_type] if prices else pkg.price_idr),
        "snapshot_at": timezone.now().isoformat(),
    }


def _create_price_line(*, booking: Booking, qty: int) -> None:
    """Baris harga snapshot (§5.2, UAT-04) — dibuat ulang selama DRAFT;
    setelah RESERVED baris dibekukan (PATCH hanya DRAFT)."""
    booking.price_lines.all().delete()
    groups = {}
    for participant in booking.participants.all():
        snapshot = participant.pricing_snapshot_json
        key = (snapshot.get("package_name", booking.departure.package.name), snapshot.get("room_type", ""), int(snapshot["unit_price_idr"]))
        groups[key] = groups.get(key, 0) + 1
    for (name, room, unit), count in sorted(groups.items()):
        BookingPriceLine.objects.create(
            tenant=booking.tenant, environment=booking.environment, booking=booking,
            item_type="package", description=f"{name} · {room}" if room else name,
            qty=count, unit_price=Decimal(unit), amount=Decimal(unit * count),
        )


def _room_choices(room_types, pilgrim_ids):
    choices = {str(key): value for key, value in (room_types or {}).items()}
    if set(choices) - {str(pid) for pid in pilgrim_ids}:
        raise ValidationError({"room_types": "Pilihan kamar harus mengacu pada peserta booking."})
    return choices


@transaction.atomic
def create_booking(
    *,
    tenant,
    environment: str,
    departure_id,
    pilgrim_ids,
    notes: str = "",
    allow_duplicate: bool = False,
    actor=None,
    room_types=None,
) -> Booking:
    """Buat booking DRAFT dengan peserta & snapshot harga (UI-07, UAT-03/04).

    Baris departure di-lock lebih dulu → duplikat jamaah + pemeriksaan
    keberangkatan diserialisasi antar-pembuat; kuota trial dikonsumsi
    SEBELUM create (§7.1.5) dalam transaksi yang sama.
    """
    pilgrims = _resolve_pilgrims(environment=environment, pilgrim_ids=pilgrim_ids)
    try:
        departure = Departure.objects.select_for_update().get(pk=departure_id)
    except (Departure.DoesNotExist, ValueError, ValidationError):
        raise ValidationError({"departure": "Keberangkatan tidak ditemukan."}) from None
    _guard_departure_bookable(departure, environment=environment)
    departure.package = TravelPackage.objects.select_for_update().prefetch_related("room_prices").get(pk=departure.package_id)
    _check_duplicate_active(
        departure=departure,
        pilgrim_ids=[p.pk for p in pilgrims],
        allow_duplicate=allow_duplicate,
    )
    # Kuota trial SEBELUM create — rollback otomatis bila create gagal (§7.1.5).
    _consume_trial_quota(tenant, len(pilgrims))

    booking = Booking(
        tenant=tenant,
        environment=environment,
        departure=departure,
        notes=(notes or "").strip(),
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    for _attempt in range(3):
        booking.code = generate_booking_code()
        try:
            with transaction.atomic():  # savepoint — IntegrityError tak meracuni transaksi
                booking.save()
            break
        except IntegrityError:
            continue  # tabrakan kode → coba sekali lagi
    else:
        raise ValidationError({"code": "Gagal membuat booking, coba lagi."})

    choices = _room_choices(room_types, [p.pk for p in pilgrims])
    for pilgrim in pilgrims:
        snapshot = _snapshot_unit_price(departure, choices.get(str(pilgrim.pk), ""))
        BookingParticipant.objects.create(
            tenant=tenant,
            environment=environment,
            booking=booking,
            pilgrim=pilgrim,
            participant_status=ParticipantStatus.DRAFT,
            saas_charge_state=SaasChargeState.NOT_ELIGIBLE,
            pricing_snapshot_json=snapshot,
        )
    _create_price_line(booking=booking, qty=len(pilgrims))
    return booking


@transaction.atomic
def update_draft_booking(
    *,
    booking_id,
    environment: str,
    departure_id=None,
    pilgrim_ids=None,
    notes: str | None = None,
    allow_duplicate: bool = False,
    room_types=None,
) -> Booking:
    """Update booking DRAFT saja (§8.3 "Detail/update draft").

    - `departure`: pindah keberangkatan → guard pendaftaran dijalankan lagi.
    - `participants`: ganti daftar — peserta yang tidak berubah TETAP (id
      `booking_passenger_id` permanen, PRD MOD-07); penambahan mengonsumsi
      kuota trial delta (TR03: pengurangan tidak mengembalikan kuota).
    - Baris harga dibuat ulang mengikuti peserta/paket terbaru (masih DRAFT,
      belum ada invoice — UAT-04 tetap terjaga karena perubahan harga paket
      tidak menyentuh booking RESERVED+).
    """
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if booking.status != BookingStatus.DRAFT:
        raise ValidationError({"status": "Hanya booking DRAFT yang dapat diubah (§8.3 update draft)."})

    departure_changed = departure_id is not None and departure_id != booking.departure_id
    if departure_id is not None and departure_changed:
        try:
            departure = Departure.objects.select_for_update().get(pk=departure_id)
        except (Departure.DoesNotExist, ValueError, ValidationError):
            raise ValidationError({"departure": "Keberangkatan tidak ditemukan."}) from None
        _guard_departure_bookable(departure, environment=environment)
        booking.departure = departure
    else:
        departure = Departure.objects.select_for_update().get(pk=booking.departure_id)
    departure.package = TravelPackage.objects.select_for_update().prefetch_related("room_prices").get(pk=departure.package_id)

    participants_changed = False
    if pilgrim_ids is not None:
        pilgrims = _resolve_pilgrims(environment=environment, pilgrim_ids=pilgrim_ids)
        _check_duplicate_active(
            departure=departure,
            pilgrim_ids=[p.pk for p in pilgrims],
            allow_duplicate=allow_duplicate,
            exclude_booking=booking,
        )
        existing = list(booking.participants.all())
        existing_ids = {p.pilgrim_id for p in existing}
        wanted_ids = {p.pk for p in pilgrims}
        removed = [p for p in existing if p.pilgrim_id not in wanted_ids]
        added = [p for p in pilgrims if p.pk not in existing_ids]
        delta = len(added) - len(removed)
        if delta > 0:
            _consume_trial_quota(booking.tenant, delta)  # TR03: tidak pernah dikurangi
        if removed:
            BookingParticipant.objects.filter(pk__in=[p.pk for p in removed]).delete()
        choices = _room_choices(room_types, wanted_ids)
        for pilgrim in added:
            BookingParticipant.objects.create(
                tenant=booking.tenant,
                environment=booking.environment,
                booking=booking,
                pilgrim=pilgrim,
                participant_status=ParticipantStatus.DRAFT,
                saas_charge_state=SaasChargeState.NOT_ELIGIBLE,
                pricing_snapshot_json=_snapshot_unit_price(departure, choices.get(str(pilgrim.pk), "")),
            )
        participants_changed = True

    current_rows = list(booking.participants.all())
    choices = _room_choices(room_types, [p.pilgrim_id for p in current_rows])
    for row in current_rows:
        requested = choices.get(str(row.pilgrim_id), row.pricing_snapshot_json.get("room_type", ""))
        if departure_changed or (str(row.pilgrim_id) in choices and requested != row.pricing_snapshot_json.get("room_type", "")):
            row.pricing_snapshot_json = _snapshot_unit_price(departure, requested)
            row.save(update_fields=["pricing_snapshot_json", "updated_at"])
            participants_changed = True

    if notes is not None:
        booking.notes = notes.strip()

    if participants_changed or departure_changed:
        _create_price_line(booking=booking, qty=booking.participants.count())
    booking.save()
    return booking


@transaction.atomic
def delete_draft_booking(*, booking_id) -> str:
    """Hapus booking DRAFT (belum menahan kursi, belum ada invoice/pembayaran).

    Peserta dan baris harga ikut terhapus (CASCADE). Kuota trial yang sudah
    terpakai tidak dikembalikan (TR03). Booking non-draf memakai pembatalan.
    """
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if booking.status != BookingStatus.DRAFT:
        raise ValidationError({"booking": "Hanya booking draf yang dapat dihapus. Booking yang sudah direservasi memakai pembatalan."})
    code = booking.code
    booking.delete()
    return code


def advance_participant(*, participant: BookingParticipant, target: str) -> BookingParticipant:
    """Advance satu peserta mengikuti graph §6.2 — dipakai layanan pembayaran
    S11/S12 (DP verified → DP_VERIFIED_PENDING_CHARGE → CONFIRMED) dan review
    (REVIEW_REQUIRED). Transisi header booking memakai jalur ladder sendiri."""
    current = participant.participant_status
    if target not in {c for c, _ in ParticipantStatus.choices}:
        raise ValidationError({"target": "Status tujuan tidak dikenal."})
    if target == current:
        raise ValidationError({"target": f"Status sudah {target}."})
    if target not in PARTICIPANT_TRANSITIONS[current]:
        raise ValidationError(
            {"target": f"Transisi peserta {current} → {target} tidak diizinkan (kontrak §6.2)."}
        )
    participant.participant_status = target
    participant.save(update_fields=["participant_status", "updated_at"])
    return participant


def _advance_participants_header(booking: Booking, *, target: str) -> None:
    """Sinkronkan peserta dengan transisi header (§6.2 ↔ MOD-07).

    Peserta yang sudah di-`CANCELED` dilewati; peserta dalam status yang tak
    cocok tangga (mis. REVIEW_REQUIRED belum diselesaikan) menolak transisi.
    """
    p_target = HEADER_PARTICIPANT_TARGET.get(target, "missing")
    if p_target == "missing":
        return  # DRAFT — peserta belum bergerak
    if p_target is None:
        return
    rows = list(BookingParticipant.objects.select_for_update().filter(booking=booking))
    if not rows and target not in (BookingStatus.CANCELED, BookingStatus.EXPIRED):
        raise ValidationError({"participants": "Booking tanpa peserta — transisi ditolak."})
    for row in rows:
        if row.participant_status == p_target:
            continue
        if p_target == ParticipantStatus.CANCELED:
            if row.participant_status in (ParticipantStatus.DEPARTED, ParticipantStatus.COMPLETED):
                raise ValidationError(
                    {"participants": f"Peserta {row.pilgrim_id} sudah berangkat — tidak dapat dibatalkan."}
                )
        else:
            expected = HEADER_PARTICIPANT_LADDER.get(row.participant_status)
            if expected != p_target:
                raise ValidationError(
                    {
                        "participants": (
                            f"Peserta {row.pilgrim_id} berstatus {row.participant_status} — "
                            f"tidak dapat di-advance ke {p_target}."
                        )
                    }
                )
        row.participant_status = p_target
        row.save(update_fields=["participant_status", "updated_at"])


@transaction.atomic
def transition_booking(
    *,
    booking_id,
    target: str,
    reason: str = "",
    actor=None,
) -> Booking:
    """Transisi status booking dengan guard MOD-07 + §6.2 + kursi atomik.

    - `CANCELED` wajib `reason` (MOD-07 cancellation policy) dan melepas
      kursi bila status menahan kursi.
    - `EXPIRED` hanya setelah pendaftaran ditutup (guard terkontrol).
    - `DEPARTED` menunggu keberangkatan benar-benar berangkat (tautan
      peserta ↔ keberangkatan).
    """
    if target not in {c for c, _ in BookingStatus.choices}:
        raise ValidationError({"target": "Status tujuan tidak dikenal."})
    if target == BookingStatus.CANCELED and not (reason or "").strip():
        raise ValidationError({"reason": "Alasan pembatalan wajib diisi."})

    booking = Booking.objects.select_for_update().get(pk=booking_id)
    current = booking.status
    if target == current:
        raise ValidationError({"target": f"Status sudah {target}."})
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ValidationError(
            {"target": f"Transisi {current} → {target} tidak diizinkan (kontrak MOD-07)."}
        )

    departure = Departure.objects.get(pk=booking.departure_id)
    seats = BookingParticipant.objects.filter(booking=booking).count()  # 1 peserta = 1 kursi

    if target == BookingStatus.RESERVED:
        _guard_departure_bookable(departure, environment=booking.environment)
        if not reserve_seats(departure.pk, seats):
            raise ValidationError(
                {"seats": f"Kursi tersedia tidak cukup untuk {seats} peserta "
                          f"(sisa {departure.available_seats}) — kursi terakhir diperebutkan (UAT-02)."}
            )
    elif target == BookingStatus.CONFIRMED:
        ok, why = dp_confirmed(booking)
        if not ok:
            raise ValidationError({"target": why})
    elif target == BookingStatus.READY_TO_DEPART:
        ok, why = documents_complete(booking)
        if not ok:
            raise ValidationError({"checklist": why})
    elif target == BookingStatus.DEPARTED:
        if departure.status not in (DepartureStatus.DEPARTED, DepartureStatus.COMPLETED):
            raise ValidationError(
                {"target": "Keberangkatan belum berangkat — booking baru dapat ditandai DEPARTED "
                           "setelah keberangkatan DEPARTED."}
            )
    elif target == BookingStatus.EXPIRED:
        if not registration_closed(departure):
            raise ValidationError(
                {"target": "EXPIRED hanya setelah pendaftaran ditutup (deadline lewat / keberangkatan ditutup)."}
            )
    elif target == BookingStatus.CANCELED and current in SEAT_CONSUMING_STATUSES:
        if not release_seats(departure.pk, seats):
            raise ValidationError({"seats": "Gagal melepas kursi keberangkatan — coba lagi."})
    if target == BookingStatus.EXPIRED and current == BookingStatus.RESERVED:
        if not release_seats(departure.pk, seats):
            raise ValidationError({"seats": "Gagal melepas kursi keberangkatan — coba lagi."})

    _advance_participants_header(booking, target=target)

    booking.status = target
    fields = ["status", "updated_at"]
    if target == BookingStatus.CANCELED:
        booking.cancel_reason = (reason or "").strip()
        booking.canceled_by = actor if getattr(actor, "is_authenticated", False) else None
        fields += ["cancel_reason", "canceled_by"]
    booking.save(update_fields=fields)
    if target == BookingStatus.RESERVED:
        from modules.notifications.services import booking_reserved

        booking_reserved(booking)  # NTF-01 "booking berhasil": kursi sudah diamankan
    if target in (BookingStatus.CANCELED, BookingStatus.EXPIRED):
        from modules.billing.services import void_pending_for_booking
        from modules.payments.services import cancel_booking_invoice

        cancel_booking_invoice(booking, reason or "Booking kedaluwarsa")
        if booking.environment == "production":
            # Charge POSTED tidak direfund otomatis (PAY09); hanya PENDING di-VOID.
            void_pending_for_booking(booking, reason or "Booking kedaluwarsa")
    return booking
