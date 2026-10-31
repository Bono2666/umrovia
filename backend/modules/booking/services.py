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

UNSET = object()

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
    taken = sorted(qs, key=lambda t: (t.pilgrim.name, t.booking.code))
    if taken:
        if len(taken) == 1:
            who = f"{taken[0].pilgrim.name} sudah punya booking aktif {taken[0].booking.code}"
        else:
            pairs = [f"{t.pilgrim.name} ({t.booking.code})" for t in taken]
            who = f"{', '.join(pairs[:-1])} dan {pairs[-1]} sudah punya booking aktif"
        raise ValidationError(
            {
                "participants": (
                    f"{who} di keberangkatan ini. Pilih jamaah atau keberangkatan lain, "
                    "atau batalkan booking tersebut terlebih dahulu."
                ),
                # Kode booking yang bentrok — klien menggulir ke barisnya.
                "conflicting_bookings": sorted({t.booking.code for t in taken}),
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


PRICE_CATEGORIES = {"ADULT": "Dewasa", "CHILD_NO_BED": "Anak tanpa kasur", "INFANT": "Bayi"}
AGE_LIMITS = {"CHILD_NO_BED": 12, "INFANT": 2}  # usia (tahun) pada tanggal berangkat


def _age_on(birth_date, day):
    return day.year - birth_date.year - ((day.month, day.day) < (birth_date.month, birth_date.day))


def _snapshot_unit_price(departure: Departure, room_type: str = "", category: str = "ADULT", addons=None, pilgrim=None) -> dict:
    """Snapshot harga per peserta (UAT-04): dewasa per tipe kamar, atau varian
    anak tanpa kasur/bayi (MOD-05), ditambah layanan tambahan pilihan."""
    pkg = departure.package
    category = category or "ADULT"
    if category not in PRICE_CATEGORIES:
        raise ValidationError({"price_categories": "Kategori harga tidak dikenal."})
    if category == "ADULT":
        prices = {row.room_type: row.price_idr for row in pkg.room_prices.all()}
        if prices and room_type not in prices:
            raise ValidationError({"room_types": "Pilih tipe kamar yang tersedia untuk setiap jamaah."})
        if not prices and room_type:
            raise ValidationError({"room_types": "Paket ini belum memiliki harga tipe kamar tersebut."})
        unit = int(prices[room_type] if prices else pkg.price_idr)
    else:
        unit = pkg.child_no_bed_price_idr if category == "CHILD_NO_BED" else pkg.infant_price_idr
        if unit is None:
            raise ValidationError({"price_categories": f"Paket ini tidak menawarkan harga {PRICE_CATEGORIES[category].lower()}."})
        room_type = ""
        birth = getattr(pilgrim, "birth_date", None)
        if birth and _age_on(birth, departure.start_at.date()) >= AGE_LIMITS[category]:
            raise ValidationError({"price_categories": f"{pilgrim.name}: usia saat berangkat tidak memenuhi kategori {PRICE_CATEGORIES[category].lower()} (< {AGE_LIMITS[category]} tahun)."})
    catalog = {row["code"]: row for row in (pkg.addons_json or [])}
    chosen = []
    for code in addons or []:
        if code not in catalog:
            raise ValidationError({"addons": f"Layanan tambahan {code} tidak tersedia pada paket ini."})
        chosen.append({"code": code, "name": catalog[code]["name"], "price_idr": int(catalog[code]["price_idr"])})
    snapshot = {
        "package_id": str(pkg.id),
        "package_code": pkg.code,
        "package_name": pkg.name,
        "room_type": room_type,
        "price_category": category,
        "unit_price_idr": int(unit),
        "snapshot_at": timezone.now().isoformat(),
    }
    if chosen:
        snapshot["addons"] = chosen
        snapshot["addons_idr"] = sum(row["price_idr"] for row in chosen)
    return snapshot


ADJUSTMENT_KEYS = ("discount_idr", "extra_idr", "adjustment_note")
MAX_ADJUSTMENT_IDR = 10_000_000_000


def participant_net(snapshot: dict) -> int:
    """Harga bersih peserta = harga paket − diskon + biaya tambahan (MOD-07 §5.2)."""
    return int(snapshot["unit_price_idr"]) - int(snapshot.get("discount_idr") or 0) + int(snapshot.get("extra_idr") or 0) + int(snapshot.get("addons_idr") or 0)


def _with_adjustment(snapshot: dict, adjustment: dict, *, label: str) -> dict:
    discount, extra = adjustment.get("discount_idr", 0) or 0, adjustment.get("extra_idr", 0) or 0
    note = str(adjustment.get("note", "") or "").strip()
    for value in (discount, extra):
        if type(value) is not int or not 0 <= value <= MAX_ADJUSTMENT_IDR:
            raise ValidationError({"adjustments": f"{label}: diskon/biaya tambahan harus Rp0–Rp10 miliar."})
    if (discount or extra) and not note:
        raise ValidationError({"adjustments": f"{label}: alasan diskon/biaya tambahan wajib diisi."})
    if len(note) > 200:
        raise ValidationError({"adjustments": f"{label}: alasan maksimal 200 karakter."})
    result = {key: value for key, value in snapshot.items() if key not in ADJUSTMENT_KEYS}
    if discount or extra:
        result.update({"discount_idr": discount, "extra_idr": extra, "adjustment_note": note})
    if participant_net(result) < 1:
        raise ValidationError({"adjustments": f"{label}: diskon tidak boleh menghabiskan seluruh harga (minimal Rp1 agar DP dapat dicatat)."})
    return result


def _carry_adjustment(old: dict, new: dict) -> dict:
    """Penyesuaian tetap melekat saat harga di-snapshot ulang (ganti kamar/keberangkatan)."""
    if not old.get("discount_idr") and not old.get("extra_idr"):
        return new
    return _with_adjustment(new, {"discount_idr": old.get("discount_idr", 0), "extra_idr": old.get("extra_idr", 0), "note": old.get("adjustment_note", "")}, label="Penyesuaian")


def apply_adjustments(*, rows, adjustments, can_discount: bool, key=lambda row: str(row.pilgrim_id)) -> bool:
    """Terapkan `{pilgrim_id: {discount_idr, extra_idr, note}}` ke snapshot peserta.

    Mengubah nilai diskon memerlukan `bookings.discount`; menyimpan ulang nilai
    yang sama tidak. Mengembalikan True bila ada snapshot yang berubah.
    """
    from rest_framework.exceptions import PermissionDenied

    choices = {str(k): v for k, v in (adjustments or {}).items()}
    by_key = {key(row): row for row in rows}
    if set(choices) - set(by_key):
        raise ValidationError({"adjustments": "Penyesuaian harus mengacu pada peserta booking."})
    changed = False
    for ident, adjustment in choices.items():
        row = by_key[ident]
        updated = _with_adjustment(row.pricing_snapshot_json, adjustment, label=row.pilgrim.name)
        if int(updated.get("discount_idr") or 0) != int(row.pricing_snapshot_json.get("discount_idr") or 0) and not can_discount:
            raise PermissionDenied("Memberi atau mengubah diskon memerlukan izin 'bookings.discount'.")
        if updated != row.pricing_snapshot_json:
            row.pricing_snapshot_json = updated
            row.save(update_fields=["pricing_snapshot_json", "updated_at"])
            changed = True
    return changed


def _create_price_line(*, booking: Booking, qty: int | None = None) -> None:
    """Baris harga snapshot (§5.2, UAT-04) — dibuat ulang selama DRAFT dan saat
    revisi invoice berotorisasi. Paket per kelompok kamar (gross) + baris
    `adjustment` per peserta untuk diskon (negatif) dan biaya tambahan."""
    booking.price_lines.all().delete()
    groups, addon_groups = {}, {}
    adjustments = []
    for participant in booking.participants.select_related("pilgrim").order_by("created_at", "id"):
        snapshot = participant.pricing_snapshot_json
        label = snapshot.get("room_type", "") or (PRICE_CATEGORIES.get(snapshot.get("price_category", ""), "") if snapshot.get("price_category", "ADULT") != "ADULT" else "")
        key = (snapshot.get("package_name", booking.departure.package.name), label, int(snapshot["unit_price_idr"]))
        groups[key] = groups.get(key, 0) + 1
        for addon in snapshot.get("addons", []):
            akey = (f"Layanan tambahan · {addon['name']}", int(addon["price_idr"]))
            addon_groups[akey] = addon_groups.get(akey, 0) + 1
        note = snapshot.get("adjustment_note", "")
        if snapshot.get("discount_idr"):
            adjustments.append((f"Diskon · {participant.pilgrim.name} ({note})", -int(snapshot["discount_idr"])))
        if snapshot.get("extra_idr"):
            adjustments.append((f"Biaya tambahan · {participant.pilgrim.name} ({note})", int(snapshot["extra_idr"])))
    for (name, room, unit), count in sorted(groups.items()):
        BookingPriceLine.objects.create(
            tenant=booking.tenant, environment=booking.environment, booking=booking,
            item_type="package", description=f"{name} · {room}" if room else name,
            qty=count, unit_price=Decimal(unit), amount=Decimal(unit * count),
        )
    for (description, unit), count in sorted(addon_groups.items()):
        BookingPriceLine.objects.create(
            tenant=booking.tenant, environment=booking.environment, booking=booking,
            item_type="addon", description=description[:200], qty=count, unit_price=Decimal(unit), amount=Decimal(unit * count),
        )
    for description, amount in adjustments:
        BookingPriceLine.objects.create(
            tenant=booking.tenant, environment=booking.environment, booking=booking,
            item_type="adjustment", description=description[:200], qty=1, unit_price=Decimal(amount), amount=Decimal(amount),
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
    payer_name: str = "",
    agent_id=None,
    adjustments=None,
    can_discount: bool = False,
    branch=None,
    price_categories=None,
    addons=None,
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
        payer_name=(payer_name or "").strip(),
        branch=branch,
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
    categories = _room_choices(price_categories, [p.pk for p in pilgrims])
    extras = _room_choices(addons, [p.pk for p in pilgrims])
    for pilgrim in pilgrims:
        key = str(pilgrim.pk)
        snapshot = _snapshot_unit_price(departure, choices.get(key, ""), categories.get(key, "ADULT"), extras.get(key), pilgrim)
        BookingParticipant.objects.create(
            tenant=tenant,
            environment=environment,
            booking=booking,
            pilgrim=pilgrim,
            participant_status=ParticipantStatus.DRAFT,
            saas_charge_state=SaasChargeState.NOT_ELIGIBLE,
            pricing_snapshot_json=snapshot,
        )
    if adjustments:
        apply_adjustments(rows=list(booking.participants.select_related("pilgrim")), adjustments=adjustments, can_discount=can_discount)
    if agent_id:
        from modules.agents.services import assign_agent

        assign_agent(booking=booking, agent_id=agent_id, actor=actor, reason="Booking dibuat")
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
    payer_name: str | None = None,
    agent_id=UNSET,
    adjustments=None,
    can_discount: bool = False,
    actor=None,
    branch=UNSET,
    price_categories=None,
    addons=None,
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
                pricing_snapshot_json=_snapshot_unit_price(
                    departure, choices.get(str(pilgrim.pk), ""), (price_categories or {}).get(str(pilgrim.pk), "ADULT"), (addons or {}).get(str(pilgrim.pk)), pilgrim,
                ),
            )
        participants_changed = True

    current_rows = list(booking.participants.select_related("pilgrim"))
    ids = [p.pilgrim_id for p in current_rows]
    choices, categories, extras = _room_choices(room_types, ids), _room_choices(price_categories, ids), _room_choices(addons, ids)
    for row in current_rows:
        key, snap = str(row.pilgrim_id), row.pricing_snapshot_json
        requested = choices.get(key, snap.get("room_type", ""))
        category = categories.get(key, snap.get("price_category", "ADULT"))
        chosen = extras[key] if key in extras else [a["code"] for a in snap.get("addons", [])]
        changed = (key in choices and requested != snap.get("room_type", "")) or category != snap.get("price_category", "ADULT") \
            or sorted(chosen) != sorted(a["code"] for a in snap.get("addons", []))
        if departure_changed or changed:
            row.pricing_snapshot_json = _carry_adjustment(snap, _snapshot_unit_price(departure, requested if category == "ADULT" else "", category, chosen, row.pilgrim))
            row.save(update_fields=["pricing_snapshot_json", "updated_at"])
            participants_changed = True

    if adjustments:
        rows = list(booking.participants.select_related("pilgrim"))
        participants_changed = apply_adjustments(rows=rows, adjustments=adjustments, can_discount=can_discount) or participants_changed

    if notes is not None:
        booking.notes = notes.strip()
    if payer_name is not None:
        booking.payer_name = payer_name.strip()
    if branch is not UNSET:
        booking.branch = branch
    if agent_id is not UNSET:
        from modules.agents.services import assign_agent

        assign_agent(booking=booking, agent_id=agent_id, actor=actor, reason="Diubah saat draf")

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
        from modules.payments.services import auto_issue_invoice

        auto_issue_invoice(booking, actor)  # INV-01: invoice otomatis saat booking sah
    if target in (BookingStatus.CONFIRMED, BookingStatus.DOCUMENT_PROCESS, BookingStatus.READY_TO_DEPART):
        from modules.notifications.services import booking_progressed

        booking_progressed(booking)
    if target in (BookingStatus.CANCELED, BookingStatus.EXPIRED):
        from modules.billing.services import void_pending_for_booking
        from modules.payments.services import cancel_booking_invoice

        cancel_booking_invoice(booking, reason or "Booking kedaluwarsa")
        if target == BookingStatus.CANCELED and current != BookingStatus.DRAFT:
            # Draf belum pernah diumumkan ke jamaah (booking.reserved terbit saat reservasi).
            from modules.notifications.services import booking_canceled

            booking_canceled(booking)
        if booking.environment == "production":
            # Charge POSTED tidak direfund otomatis (PAY09); hanya PENDING di-VOID.
            void_pending_for_booking(booking, reason or "Booking kedaluwarsa")
    if booking.agent_id or target in (BookingStatus.CANCELED, BookingStatus.EXPIRED):
        from modules.agents.services import sync_commission

        sync_commission(booking, reason=reason or "Booking kedaluwarsa")
    return booking


# ------------------------------------------------------------ daftar tunggu --
@transaction.atomic
def add_to_waitlist(*, tenant, environment, departure_id, pilgrim_id, room_type="", notes="", actor=None):
    """MOD-06: daftar tunggu hanya untuk keberangkatan OPEN yang kursinya habis."""
    from modules.booking.models import WaitlistEntry, WaitlistStatus

    try:
        departure = Departure.objects.select_for_update().get(pk=departure_id)
    except (Departure.DoesNotExist, ValueError, ValidationError):
        raise ValidationError({"departure": "Keberangkatan tidak ditemukan."}) from None
    _guard_departure_bookable(departure, environment=environment)
    if departure.available_seats > 0:
        raise ValidationError({"departure": f"Masih ada {departure.available_seats} kursi — buat booking langsung."})
    pilgrim = _resolve_pilgrims(environment=environment, pilgrim_ids=[pilgrim_id])[0]
    _check_duplicate_active(departure=departure, pilgrim_ids=[pilgrim.pk], allow_duplicate=False)
    if room_type:
        _snapshot_unit_price(departure.__class__.objects.select_related("package").get(pk=departure.pk), room_type)
    if WaitlistEntry.objects.filter(departure=departure, pilgrim=pilgrim, status=WaitlistStatus.WAITING).exists():
        raise ValidationError({"pilgrim": "Jamaah sudah ada di daftar tunggu keberangkatan ini."})
    return WaitlistEntry.objects.create(
        tenant=tenant, environment=environment, departure=departure, pilgrim=pilgrim, room_type=room_type,
        notes=(notes or "").strip()[:240], created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )


def waitlist_position(entry) -> int:
    from modules.booking.models import WaitlistEntry, WaitlistStatus

    return WaitlistEntry.objects.filter(departure_id=entry.departure_id, status=WaitlistStatus.WAITING, created_at__lt=entry.created_at).count() + 1


@transaction.atomic
def book_from_waitlist(*, entry_id, actor=None, branch=None):
    """Buat booking DRAFT dari entri (urut antrean: posisi N butuh ≥ N kursi tersedia)."""
    from modules.booking.models import WaitlistEntry, WaitlistStatus

    entry = WaitlistEntry.objects.select_for_update().select_related("departure").get(pk=entry_id)
    if entry.status != WaitlistStatus.WAITING:
        raise ValidationError({"status": "Entri daftar tunggu sudah diproses."})
    departure = Departure.objects.get(pk=entry.departure_id)
    position = waitlist_position(entry)
    if departure.available_seats < position:
        raise ValidationError({"departure": f"Posisi antrean {position}; kursi tersedia {departure.available_seats}. Proses antrean di depannya lebih dulu."})
    booking = create_booking(
        tenant=entry.tenant, environment=entry.environment, departure_id=entry.departure_id, pilgrim_ids=[entry.pilgrim_id],
        notes=f"Dari daftar tunggu. {entry.notes}".strip(), actor=actor,
        room_types={str(entry.pilgrim_id): entry.room_type} if entry.room_type else None, branch=branch,
    )
    entry.status, entry.booking = WaitlistStatus.BOOKED, booking
    entry.save(update_fields=["status", "booking", "updated_at"])
    return entry


@transaction.atomic
def cancel_waitlist(*, entry_id, reason):
    from modules.booking.models import WaitlistEntry, WaitlistStatus

    entry = WaitlistEntry.objects.select_for_update().get(pk=entry_id)
    if entry.status != WaitlistStatus.WAITING:
        raise ValidationError({"status": "Entri daftar tunggu sudah diproses."})
    if not (reason or "").strip():
        raise ValidationError({"reason": "Alasan wajib diisi."})
    entry.status, entry.cancel_reason = WaitlistStatus.CANCELED, reason.strip()[:240]
    entry.save(update_fields=["status", "cancel_reason", "updated_at"])
    return entry
