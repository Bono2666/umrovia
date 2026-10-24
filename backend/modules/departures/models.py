"""Keberangkatan & kuota kursi (Spec §5.2 `departures`, §6.5; PRD MOD-06).

Aturan:
- Tabel bisnis tenant+environment → RLS sejak migrasi pertama (ADR-0003 §3).
- **Seat counter atomik (BR-002, UAT-02):** `seats_taken` di-baris departure
  dan hanya boleh berubah lewat `services.reserve_seats/release_seats` yang
  meng-update dengan guard WHERE sehingga baris terkunci — dua pemesan
  serentak pada kursi terakhir → tepat satu menang. `seats_taken` = cache
  seperti `balance_cached_idr` wallet (§5.4) — rekonsiliasi vs booking ada di
  S09. CHECK constraint `seats_taken + seats_blocked <= seat_capacity`
  menjamin ketersediaan tidak negatif di level DB (BR-002).
- Status mengikuti kontrak state machine §6.5:
  `DRAFT → OPEN → READY → DEPARTED → COMPLETED` atau `CANCELED`.
  Pemetaan MOD-06: FULL ≡ `available == 0` (turunan, bukan status tersimpan),
  CLOSED ≡ pendaftaran tertutup (deadline/READY+, turunan), PREPARATION ≡ READY.
- `departure_events` append-only: setiap transisi mencatat prior/next/actor/
  reason (§5.2) — pelengkap `audit_events`.
"""
import uuid

from django.core.exceptions import ValidationError
from django.db import models

from common.models import BaseAppModel
from modules.tenants.managers import TenantScopedModel


class DepartureStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    OPEN = "OPEN", "Pendaftaran dibuka"
    READY = "READY", "Siap berangkat"
    DEPARTED = "DEPARTED", "Sudah berangkat"
    COMPLETED = "COMPLETED", "Selesai"
    CANCELED = "CANCELED", "Dibatalkan"


class Departure(TenantScopedModel, BaseAppModel):
    """Satu jadwal keberangkatan untuk satu paket (MOD-06)."""

    environment = models.CharField(
        max_length=16, choices=[("demo", "Demo"), ("production", "Produksi")]
    )
    code = models.CharField(max_length=32)  # auto DPR-<8hex>
    package = models.ForeignKey(
        "catalog.TravelPackage", on_delete=models.PROTECT, related_name="departures"
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField(null=True, blank=True)
    city_of_origin = models.CharField(max_length=100, default="")
    route = models.CharField(max_length=120, blank=True, default="")  # maskapai/rute (opsional)
    meeting_point = models.CharField(max_length=160, blank=True, default="")
    seat_capacity = models.PositiveIntegerField(default=0)
    seats_blocked = models.PositiveIntegerField(default=0)  # kuota blokir (MOD-06)
    seats_taken = models.PositiveIntegerField(default=0)  # counter atomik (BR-002)
    registration_deadline = models.DateField(null=True, blank=True)
    lead_staff = models.ForeignKey(
        "identity.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="led_departures",
    )
    status = models.CharField(max_length=16, choices=DepartureStatus.choices, default=DepartureStatus.DRAFT)
    notes = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "keberangkatan"
        verbose_name_plural = "keberangkatan"
        ordering = ["start_at", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "environment", "code"], name="uq_departure_code"
            ),
            models.CheckConstraint(
                condition=models.Q(seat_capacity__gte=0), name="ck_departure_capacity_nonneg"
            ),
            models.CheckConstraint(
                condition=models.Q(seats_blocked__gte=0), name="ck_departure_blocked_nonneg"
            ),
            # BR-002: kursi terpakai + terblokir tidak pernah melebihi kapasitas
            # → ketersediaan (kapasitas − terpakai − terblokir) tidak negatif.
            models.CheckConstraint(
                condition=models.Q(seats_taken__lte=models.F("seat_capacity") - models.F("seats_blocked")),
                name="ck_departure_seats_within_capacity",
            ),
        ]

    @property
    def available_seats(self) -> int:
        """Kursi tersedia: kapasitas − terpakai − terblokir (formula MOD-06)."""
        return max(self.seat_capacity - self.seats_taken - self.seats_blocked, 0)

    def __str__(self) -> str:
        return f"{self.code} ({self.package_id})"


class DepartureEvent(TenantScopedModel, BaseAppModel):
    """Riwayat transisi status keberangkatan (§5.2) — append-only."""

    departure = models.ForeignKey(Departure, on_delete=models.CASCADE, related_name="events")
    environment = models.CharField(max_length=16, choices=[("demo", "Demo"), ("production", "Produksi")])
    prior_status = models.CharField(max_length=16)
    next_status = models.CharField(max_length=16)
    actor = models.ForeignKey(
        "identity.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="departure_events"
    )
    reason = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "event keberangkatan"
        verbose_name_plural = "event keberangkatan"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("departure_events bersifat append-only (Spec §5.2).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("departure_events bersifat append-only (Spec §5.2).")

    def __str__(self) -> str:
        return f"{self.departure_id} {self.prior_status}→{self.next_status}"


def generate_departure_code() -> str:
    """Kode keberangkatan auto (pola PKT-/JM- sebelumnya)."""
    return f"DPR-{uuid.uuid4().hex[:8].upper()}"
