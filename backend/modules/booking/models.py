"""Booking & peserta (Spec §5.2 `bookings`/`booking_participants`/
`booking_price_lines`, §6.2; PRD MOD-07).

Aturan:
- Tabel bisnis tenant+environment → RLS sejak migrasi pertama (ADR-0003 §3).
- `code` auto `BK-<8hex>`, UNIQUE(tenant, environment, code) — §5.2
  "UNIQUE composite code"; tidak global-unique lintas tenant.
- Status header mengikuti MOD-07:
  `DRAFT → RESERVED → CONFIRMED → DOCUMENT_PROCESS → READY_TO_DEPART →
  DEPARTED → COMPLETED`, dengan `CANCELED` (alasan wajib) dan `EXPIRED`
  (terminal terkontrol — hanya setelah pendaftaran ditutup).
- Peserta mengikuti state machine §6.2: `DRAFT → REGISTERED → AWAITING_DP →
  DP_VERIFIED_PENDING_CHARGE → CONFIRMED → READY → DEPARTED → COMPLETED` +
  `CANCELED`/`REVIEW_REQUIRED`. Tahap DP dimiliki modul pembayaran (S11/S12).
- `booking_passenger_id` UUID permanen (PRD MOD-07 booking-saverules) = unit
  billing "booking-jamaah" (POL-02/POL-04) — bukan master jamaah.
  `saas_charge_state` default `not_eligible` (diisi S12), `dp_eligible_at`
  diisi S11.
- Kursi: 1 peserta = 1 kursi. `seats_taken` departure HANYA berubah lewat
  `services.reserve_seats/release_seats` (BR-002) pada transisi
  DRAFT→RESERVED (reserve) dan CANCELED/EXPIRED dari RESERVED (release).
- Snapshot harga per peserta (`pricing_snapshot_json`) + baris
  `booking_price_lines` dibuat saat booking — perubahan harga paket
  sesudahnya tidak menyentuh booking existing (UAT-04/MOD-05).
"""
import uuid

from django.db import models

from common.models import BaseAppModel
from modules.tenants.managers import TenantScopedModel


class BookingStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    RESERVED = "RESERVED", "Direservasi"
    CONFIRMED = "CONFIRMED", "Terkonfirmasi"
    DOCUMENT_PROCESS = "DOCUMENT_PROCESS", "Proses dokumen"
    READY_TO_DEPART = "READY_TO_DEPART", "Siap berangkat"
    DEPARTED = "DEPARTED", "Sudah berangkat"
    COMPLETED = "COMPLETED", "Selesai"
    CANCELED = "CANCELED", "Dibatalkan"
    EXPIRED = "EXPIRED", "Kedaluwarsa"


class ParticipantStatus(models.TextChoices):
    """State machine peserta (Spec §6.2)."""

    DRAFT = "DRAFT", "Draft"
    REGISTERED = "REGISTERED", "Terdaftar"
    AWAITING_DP = "AWAITING_DP", "Menunggu DP"
    DP_VERIFIED_PENDING_CHARGE = "DP_VERIFIED_PENDING_CHARGE", "DP terverifikasi — charge tertunda"
    CONFIRMED = "CONFIRMED", "Terkonfirmasi"
    READY = "READY", "Siap berangkat"
    DEPARTED = "DEPARTED", "Sudah berangkat"
    COMPLETED = "COMPLETED", "Selesai"
    CANCELED = "CANCELED", "Dibatalkan"
    REVIEW_REQUIRED = "REVIEW_REQUIRED", "Perlu review"


class SaasChargeState(models.TextChoices):
    """Status charge SaaS per booking-jamaah (PRD MOD-07 booking-saverules)."""

    NOT_ELIGIBLE = "not_eligible", "Belum eligible"
    PENDING_CHARGE = "pending_charge", "Charge tertunda"
    CHARGED = "charged", "Tercharge"
    WAIVED = "waived", "Diwaive"
    REVERSED = "reversed", "Reversed"


class Booking(TenantScopedModel, BaseAppModel):
    """Satu booking pada satu keberangkatan, berisi ≥ 1 peserta (UAT-03)."""

    environment = models.CharField(
        max_length=16, choices=[("demo", "Demo"), ("production", "Produksi")]
    )
    code = models.CharField(max_length=32)  # auto BK-<8hex>
    departure = models.ForeignKey(
        "departures.Departure", on_delete=models.PROTECT, related_name="bookings"
    )
    status = models.CharField(max_length=24, choices=BookingStatus.choices, default=BookingStatus.DRAFT)
    booked_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, default="")
    # MOD-07: pembayar (nama pada invoice) & agen yang mendapat kredit penjualan (MOD-10).
    payer_name = models.CharField(max_length=160, blank=True, default="")
    agent = models.ForeignKey(
        "agents.Agent", null=True, blank=True, on_delete=models.PROTECT, related_name="bookings"
    )
    branch = models.ForeignKey(
        "tenants.Branch", null=True, blank=True, on_delete=models.PROTECT, related_name="bookings"
    )
    cancel_reason = models.TextField(blank=True, default="")
    canceled_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="canceled_bookings",
    )
    created_by = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_bookings",
    )

    class Meta:
        verbose_name = "booking"
        verbose_name_plural = "bookings"
        ordering = ["-booked_at", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "environment", "code"], name="uq_booking_code"
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "environment", "departure", "status"],
                name="ix_booking_dep_status",
            ),
        ]

    @property
    def participant_count(self) -> int:
        return self.participants.count()

    def __str__(self) -> str:
        return f"{self.code} ({self.departure_id})"


class BookingParticipant(TenantScopedModel, BaseAppModel):
    """Peserta booking — unit "booking-jamaah" (POL-02/POL-04, §6.2).

    UNIQUE(booking_id, pilgrim_id) (§5.2): satu jamaah maksimal sekali dalam
    satu booking. Satu jamaah hanya boleh punya SATU booking aktif per
    keberangkatan (MOD-07, divalidasi aplikasi di bawah lock baris departure
    — lintas tabel sehingga constraint parsial DB tidak dapat dipakai).
    """

    environment = models.CharField(
        max_length=16, choices=[("demo", "Demo"), ("production", "Produksi")]
    )
    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, related_name="participants"
    )
    pilgrim = models.ForeignKey(
        "pilgrims.Pilgrim", on_delete=models.PROTECT, related_name="booking_participations"
    )
    booking_passenger_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False
    )  # permanen (PRD MOD-07) — referensi charge/invoice mendatang
    participant_status = models.CharField(
        max_length=32, choices=ParticipantStatus.choices, default=ParticipantStatus.DRAFT
    )
    saas_charge_state = models.CharField(
        max_length=16, choices=SaasChargeState.choices, default=SaasChargeState.NOT_ELIGIBLE
    )
    dp_eligible_at = models.DateTimeField(null=True, blank=True)
    pricing_snapshot_json = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "peserta booking"
        verbose_name_plural = "peserta booking"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "pilgrim"], name="uq_booking_pilgrim"
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "environment", "pilgrim", "participant_status"],
                name="ix_bpart_pilgrim_status",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.booking_id} → {self.pilgrim_id}"


class BookingPriceLine(TenantScopedModel, BaseAppModel):
    """Snapshot harga booking (§5.2) — dasar invoice S11, bebas perubahan
    harga paket sesudah booking (UAT-04)."""

    environment = models.CharField(
        max_length=16, choices=[("demo", "Demo"), ("production", "Produksi")]
    )
    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, related_name="price_lines"
    )
    item_type = models.CharField(
        max_length=24,
        choices=[("package", "Paket"), ("adjustment", "Penyesuaian")],
        default="package",
    )
    description = models.CharField(max_length=200)
    qty = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=15, decimal_places=2)
    amount = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        verbose_name = "baris harga booking"
        verbose_name_plural = "baris harga booking"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.booking_id} {self.description} ×{self.qty}"


def generate_booking_code() -> str:
    return f"BK-{uuid.uuid4().hex[:8].upper()}"


class WaitlistStatus(models.TextChoices):
    WAITING = "WAITING", "Menunggu kursi"
    BOOKED = "BOOKED", "Sudah dibuatkan booking"
    CANCELED = "CANCELED", "Dibatalkan"


class WaitlistEntry(TenantScopedModel, BaseAppModel):
    """Daftar tunggu keberangkatan penuh (MOD-06). Urutan = waktu masuk.

    Tidak menahan kursi. Saat kursi tersedia kembali, petugas membuat booking
    dari entri (urutan teratas lebih dulu) dan entri ditandai BOOKED.
    """

    environment = models.CharField(max_length=16)
    departure = models.ForeignKey("departures.Departure", on_delete=models.PROTECT, related_name="waitlist")
    pilgrim = models.ForeignKey("pilgrims.Pilgrim", on_delete=models.PROTECT, related_name="waitlist_entries")
    room_type = models.CharField(max_length=16, blank=True, default="")
    notes = models.CharField(max_length=240, blank=True, default="")
    status = models.CharField(max_length=16, choices=WaitlistStatus.choices, default=WaitlistStatus.WAITING)
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    cancel_reason = models.CharField(max_length=240, blank=True, default="")
    created_by = models.ForeignKey("identity.User", null=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["departure", "pilgrim"], condition=models.Q(status="WAITING"), name="uq_waitlist_waiting_pilgrim"),
        ]
