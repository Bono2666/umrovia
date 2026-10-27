"""S09 — Booking end-to-end (exit gate S09: "Booking end-to-end";
Spec §5.2/§6.2/§8.3/UI-07; PRD MOD-07, BR-002, UAT-03/UAT-04, POL-08).

Membuktikan:
- CRUD booking: kode auto `BK-`, create → DRAFT (BELUM menahan kursi),
  peserta unik ≥ 1 dalam satu booking (UAT-03), snapshot harga + baris
  `booking_price_lines` (UAT-04: perubahan harga paket sesudah booking
  tidak mengubah booking existing);
- state machine MOD-07 header (DRAFT→RESERVED→CONFIRMED→DOCUMENT_PROCESS→
  READY_TO_DEPART→DEPARTED→COMPLETED; CANCELED alasan wajib; EXPIRED hanya
  setelah pendaftaran ditutup) + sinkronisasi peserta §6.2;
- kursi atomik: DRAFT→RESERVED `reserve_seats(n)` — dua staf serentak pada
  kursi terakhir → tepat satu menang (UAT-02 di level booking); CANCELED/
  EXPIRED dari RESERVED melepas kursi; booking DEPARTED menunggu
  keberangkatan berangkat (tautan peserta ↔ departure);
- guard pembuatan: departure harus OPEN, belum lewat deadline/berangkat;
  satu jamaah satu booking AKTIF per keberangkatan (MOD-07) + override
  `allow_duplicate`; PATCH hanya DRAFT (§8.3 update draft);
- kuota trial per booking-jamaah (POL-08, §7.1.5: increment SEBELUM create,
  rollback bila gagal, tidak pernah dikurangi);
- RBAC §8.3 (Sales/Admin tulis, Ops baca, Finance tanpa bookings.*), IDOR
  404, environment read-only (§2.2), RLS ENABLE+FORCE 3 tabel (§5.6).
"""
from contextlib import contextmanager
from datetime import timedelta
from threading import Barrier, Thread
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection
from django.utils import timezone

from modules.audit.models import AuditEvent
from modules.booking.models import (
    Booking,
    BookingParticipant,
    BookingPriceLine,
    BookingStatus,
    ParticipantStatus,
    generate_booking_code,
)
from modules.booking.services import advance_participant, create_booking, transition_booking
from modules.catalog.models import TravelPackage
from modules.departures.models import Departure, DepartureStatus
from modules.identity.models import User, UserStatus
from modules.pilgrims.models import Pilgrim
from modules.tenants.context import clear_current_tenant, set_current_tenant
from modules.tenants.models import (
    Environment,
    EnvironmentState,
    MembershipStatus,
    Role,
    Tenant,
    TenantEnvironment,
    TenantMembership,
)
from modules.trial.models import TenantTrial, TrialStatus


@contextmanager
def _as_tenant(tenant):
    token = set_current_tenant(tenant)
    try:
        yield
    finally:
        clear_current_tenant(token)


def _csrf(client) -> str:
    return client.get("/api/v1/auth/csrf").json()["csrfToken"]


def _seed_env(tenant, environment: str = Environment.DEMO, state: str = EnvironmentState.ACTIVE):
    return TenantEnvironment.objects.create(tenant=tenant, environment=environment, state=state)


def _make_member(client, email: str, tenant, role_name: str, perms: list) -> User:
    member = User.objects.create_user(email=email, password="rahasia123")
    member.status = UserStatus.ACTIVE
    member.email_verified_at = timezone.now()
    member.save()
    role, _created = Role.objects.get_or_create(
        tenant=tenant, name=role_name, defaults={"permissions_json": perms}
    )
    TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant, user=member, role=role, status=MembershipStatus.ACTIVE
    )
    client.force_login(member)
    return member


def _seed_package(tenant, *, price_idr: int = 45_000_000, code: str | None = None) -> TravelPackage:
    with _as_tenant(tenant):
        return TravelPackage.objects.create(
            tenant=tenant,
            environment=Environment.DEMO,
            code=code or f"PKT-{uuid4().hex[:8].upper()}",
            name="Paket Umroh",
            price_idr=price_idr,
        )


def _seed_departure(
    tenant,
    *,
    package: TravelPackage | None = None,
    capacity: int = 10,
    status: str = DepartureStatus.OPEN,
    start_in_days: int = 30,
    deadline_in_days: int | None = None,
) -> Departure:
    if package is None:
        package = _seed_package(tenant)
    deadline = None
    if deadline_in_days is not None:
        deadline = timezone.localdate() + timedelta(days=deadline_in_days)
    with _as_tenant(tenant):
        return Departure.objects.create(
            tenant=tenant,
            environment=Environment.DEMO,
            code=f"DPR-{uuid4().hex[:8].upper()}",
            package=package,
            start_at=timezone.now() + timedelta(days=start_in_days),
            city_of_origin="Jakarta",
            seat_capacity=capacity,
            registration_deadline=deadline,
            status=status,
        )


def _seed_pilgrim(tenant, name: str, *, environment: str = Environment.DEMO) -> Pilgrim:
    with _as_tenant(tenant):
        return Pilgrim.objects.create(
            tenant=tenant,
            environment=environment,
            code=f"JM-{uuid4().hex[:8].upper()}",
            name=name,
        )


def _create(client, departure, pilgrims, **extra) -> dict:
    csrf = _csrf(client)
    body = {
        "departure": str(departure.pk),
        "participants": [str(getattr(p, "pk", p)) for p in pilgrims],
        **extra,
    }
    return client.post("/api/v1/bookings", body, content_type="application/json", HTTP_X_CSRFTOKEN=csrf)


def _transition(client, booking_id, target: str, reason: str = "") -> dict:
    csrf = _csrf(client)
    body = {"target": target}
    if reason:
        body["reason"] = reason
    return client.post(
        f"/api/v1/bookings/{booking_id}/transition",
        body,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


def _dep(tenant, departure_id) -> Departure:
    return Departure.objects.without_tenant_guard().get(pk=departure_id)


def _booking(booking_id) -> Booking:
    return Booking.objects.without_tenant_guard().get(pk=booking_id)


# ------------------------------------------------------- create (UI-07) --


@pytest.mark.django_db
def test_create_booking_e2e_uat03(auth_client, tenant_a):
    """Create → DRAFT, kode BK-, 3 peserta unik (UAT-03), snapshot harga,
    belum menahan kursi, audit tercatat."""
    _seed_env(tenant_a)
    pkg = _seed_package(tenant_a, price_idr=45_000_000)
    dep = _seed_departure(tenant_a, package=pkg, capacity=40)
    pilgrims = [_seed_pilgrim(tenant_a, n) for n in ("Budi", "Sari", "Asep")]

    response = _create(auth_client, dep, pilgrims, notes="Keluarga 1")
    assert response.status_code == 201, response.content
    payload = response.json()

    assert payload["code"].startswith("BK-")
    assert payload["status"] == BookingStatus.DRAFT
    assert payload["environment"] == Environment.DEMO
    assert payload["departure_id"] == str(dep.pk)
    assert payload["departure_code"] == dep.code
    assert payload["participant_count"] == 3
    # UAT-03: satu booking, tiga participant unik
    assert len({p["pilgrim_id"] for p in payload["participants"]}) == 3
    assert {p["pilgrim_name"] for p in payload["participants"]} == {"Budi", "Sari", "Asep"}
    assert all(p["participant_status"] == ParticipantStatus.DRAFT for p in payload["participants"])
    assert all(p["saas_charge_state"] == "not_eligible" for p in payload["participants"])
    assert all(p["booking_passenger_id"] for p in payload["participants"])
    assert all(p["pricing_snapshot"]["unit_price_idr"] == 45_000_000 for p in payload["participants"])
    # snapshot harga: 1 baris × 3 (UAT-04 basis)
    assert len(payload["price_lines"]) == 1
    line = payload["price_lines"][0]
    assert line["qty"] == 3
    assert line["unit_price"] == 45_000_000.0
    assert payload["total_amount"] == 135_000_000.0
    # DRAFT belum menahan kursi (reservasi terjadi di DRAFT→RESERVED)
    assert _dep(tenant_a, dep.pk).seats_taken == 0
    assert payload["available_seats"] == 40

    assert AuditEvent.objects.filter(action="bookings.created", tenant=tenant_a).exists()


@pytest.mark.django_db
def test_uat04_price_change_after_booking_keeps_lines(auth_client, tenant_a):
    """UAT-04: harga paket berubah sesudah booking → baris & snapshot booking
    lama tidak berubah; booking baru memakai harga baru."""
    _seed_env(tenant_a)
    pkg = _seed_package(tenant_a, price_idr=45_000_000)
    dep = _seed_departure(tenant_a, package=pkg, capacity=40)
    a = _seed_pilgrim(tenant_a, "Amda")
    b = _seed_pilgrim(tenant_a, "Bagas")

    first = _create(auth_client, dep, [a])
    assert first.status_code == 201
    bid = first.json()["id"]

    pkg = TravelPackage.objects.without_tenant_guard().get(pk=pkg.pk)
    pkg.price_idr = 60_000_000
    pkg.save(update_fields=["price_idr", "updated_at"])

    old = auth_client.get(f"/api/v1/bookings/{bid}").json()
    assert old["price_lines"][0]["unit_price"] == 45_000_000.0
    assert old["total_amount"] == 45_000_000.0
    assert old["participants"][0]["pricing_snapshot"]["unit_price_idr"] == 45_000_000
    # snapshot juga tertuang di tabel `booking_price_lines` (§5.2)
    rows = BookingPriceLine.objects.without_tenant_guard().filter(booking_id=bid)
    assert rows.count() == 1
    assert rows.first().unit_price == 45_000_000
    assert rows.first().amount == 45_000_000

    second = _create(auth_client, dep, [b])
    assert second.status_code == 201
    assert second.json()["price_lines"][0]["unit_price"] == 60_000_000.0


@pytest.mark.django_db
def test_create_participant_validation(auth_client, tenant_a):
    """Peserta: minimal 1, unik, harus ada & satu environment (§5.2)."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a, capacity=10)
    a = _seed_pilgrim(tenant_a, "A")

    empty = _create(auth_client, dep, [])
    assert empty.status_code == 400
    assert "participants" in empty.json()["field_errors"]

    dup = _create(auth_client, dep, [a, a])
    assert dup.status_code == 400

    ghost = _create(auth_client, dep, [a, uuid4()])
    assert ghost.status_code == 400

    foreign_env = _seed_pilgrim(tenant_a, "ProdOnly", environment=Environment.PRODUCTION)
    cross = _create(auth_client, dep, [foreign_env])
    assert cross.status_code == 400
    assert "environment" in str(cross.json())


@pytest.mark.django_db
def test_create_guards_departure_closed(auth_client, tenant_a):
    """Pendaftaran hanya pada keberangkatan OPEN & belum lewat deadline
    (MOD-06/§10.1)."""
    _seed_env(tenant_a)
    a = _seed_pilgrim(tenant_a, "A")

    draft = _seed_departure(tenant_a, status=DepartureStatus.DRAFT)
    assert _create(auth_client, draft, [a]).status_code == 400

    ready = _seed_departure(tenant_a, status=DepartureStatus.READY)
    assert _create(auth_client, ready, [a]).status_code == 400

    passed = _seed_departure(tenant_a, deadline_in_days=-1)
    resp = _create(auth_client, passed, [a])
    assert resp.status_code == 400
    assert "lewat" in str(resp.json())

    departed = _seed_departure(tenant_a, start_in_days=-1)
    assert _create(auth_client, departed, [a]).status_code == 400


@pytest.mark.django_db
def test_duplicate_active_booking_per_pilgrim_mod07(auth_client, tenant_a):
    """MOD-07: satu jamaah satu booking AKTIF per keberangkatan; override
    eksplisit `allow_duplicate`; setelah CANCELED booking ulang diizinkan."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a, capacity=10)
    other_dep = _seed_departure(tenant_a, capacity=10)
    a = _seed_pilgrim(tenant_a, "A")

    first = _create(auth_client, dep, [a])
    assert first.status_code == 201

    clash = _create(auth_client, dep, [a])
    assert clash.status_code == 400
    assert "booking aktif" in str(clash.json())

    override = _create(auth_client, dep, [a], allow_duplicate=True)
    assert override.status_code == 201

    # keberangkatan lain bebas (unit charge terpisah, POL-08 §unit charging)
    assert _create(auth_client, other_dep, [a]).status_code == 201

    # batalkan booking pertama → masih ada booking aktif override → tetap ditolak
    canceled = _transition(auth_client, first.json()["id"], BookingStatus.CANCELED, "Ubah rencana")
    assert canceled.status_code == 200
    assert _create(auth_client, dep, [a]).status_code == 400

    # batalkan yang override → booking ulang diizinkan
    assert _transition(auth_client, override.json()["id"], BookingStatus.CANCELED, "Lepas").status_code == 200
    rebook = _create(auth_client, dep, [a])
    assert rebook.status_code == 201
    assert rebook.json()["status"] == BookingStatus.DRAFT


# ------------------------------------------------- state machine MOD-07 --


@pytest.mark.django_db
def test_status_chain_end_to_end(auth_client, tenant_a, settle_demo_dp):
    """DRAFT→RESERVED→CONFIRMED→DOCUMENT_PROCESS→READY_TO_DEPART→DEPARTED→
    COMPLETED; peserta §6.2 sinkron; booking DEPARTED menunggu departure."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a, capacity=10)
    pilgrims = [_seed_pilgrim(tenant_a, n) for n in ("Budi", "Sari")]
    bid = _create(auth_client, dep, pilgrims).json()["id"]

    # transisi ilegal dari DRAFT ditolak (MOD-07)
    assert _transition(auth_client, bid, BookingStatus.CONFIRMED).status_code == 400
    assert _transition(auth_client, bid, BookingStatus.COMPLETED).status_code == 400

    # DRAFT → RESERVED: kursi di-reserve atomik (n = peserta)
    ok = _transition(auth_client, bid, BookingStatus.RESERVED)
    assert ok.status_code == 200, ok.content
    assert ok.json()["status"] == BookingStatus.RESERVED
    assert _dep(tenant_a, dep.pk).seats_taken == 2
    assert ok.json()["available_seats"] == 8
    statuses = {p["pilgrim_name"]: p["participant_status"] for p in ok.json()["participants"]}
    assert set(statuses.values()) == {ParticipantStatus.AWAITING_DP}  # INV-01: invoice otomatis terbit

    settle_demo_dp(auth_client, bid)
    ok = _transition(auth_client, bid, BookingStatus.CONFIRMED)
    assert ok.status_code == 200
    assert all(p["participant_status"] == ParticipantStatus.CONFIRMED for p in ok.json()["participants"])

    ok = _transition(auth_client, bid, BookingStatus.DOCUMENT_PROCESS)
    assert ok.status_code == 200
    assert all(p["participant_status"] == ParticipantStatus.CONFIRMED for p in ok.json()["participants"])

    ok = _transition(auth_client, bid, BookingStatus.READY_TO_DEPART)
    assert ok.status_code == 200
    assert all(p["participant_status"] == ParticipantStatus.READY for p in ok.json()["participants"])

    # guard tautan: booking belum boleh DEPARTED selama keberangkatan belum
    early = _transition(auth_client, bid, BookingStatus.DEPARTED)
    assert early.status_code == 400
    assert "Keberangkatan belum berangkat" in str(early.json())

    Departure.objects.without_tenant_guard().filter(pk=dep.pk).update(
        status=DepartureStatus.DEPARTED
    )
    ok = _transition(auth_client, bid, BookingStatus.DEPARTED)
    assert ok.status_code == 200
    assert all(p["participant_status"] == ParticipantStatus.DEPARTED for p in ok.json()["participants"])

    done = _transition(auth_client, bid, BookingStatus.COMPLETED)
    assert done.status_code == 200
    assert all(p["participant_status"] == ParticipantStatus.COMPLETED for p in done.json()["participants"])
    # kursi tetap terpakai (pelepasan hanya CANCELED/EXPIRED)
    assert _dep(tenant_a, dep.pk).seats_taken == 2
    # terminal
    assert _transition(auth_client, bid, BookingStatus.CANCELED, "x").status_code == 400

    transitions = AuditEvent.objects.filter(action="bookings.transitioned", tenant=tenant_a)
    assert transitions.count() == 6


@pytest.mark.django_db
def test_cancel_requires_reason_and_releases_seats(auth_client, tenant_a):
    """CANCELED: alasan wajib (MOD-07), melepas kursi, peserta CANCELED."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a, capacity=5)
    pilgrims = [_seed_pilgrim(tenant_a, n) for n in ("Budi", "Sari")]
    bid = _create(auth_client, dep, pilgrims).json()["id"]

    no_reason = _transition(auth_client, bid, BookingStatus.CANCELED)
    assert no_reason.status_code == 400
    assert "reason" in no_reason.json()["field_errors"]

    assert _transition(auth_client, bid, BookingStatus.RESERVED).status_code == 200
    assert _dep(tenant_a, dep.pk).seats_taken == 2

    canceled = _transition(auth_client, bid, BookingStatus.CANCELED, "Jamaah batal berangkat")
    assert canceled.status_code == 200
    assert canceled.json()["cancel_reason"] == "Jamaah batal berangkat"
    assert canceled.json()["status"] == BookingStatus.CANCELED
    assert _dep(tenant_a, dep.pk).seats_taken == 0  # dilepas atomik
    assert all(p["participant_status"] == ParticipantStatus.CANCELED for p in canceled.json()["participants"])
    logged = AuditEvent.objects.filter(action="bookings.transitioned", tenant=tenant_a).first()
    assert logged.changes_json.get("reason") == "Jamaah batal berangkat"

    # cancel dari DRAFT: tidak ada kursi yang dipegang → tidak ada pelepasan
    b2 = _create(auth_client, dep, [_seed_pilgrim(tenant_a, "C")]).json()["id"]
    assert _transition(auth_client, b2, BookingStatus.CANCELED, "Draft dibuang").status_code == 200
    assert _dep(tenant_a, dep.pk).seats_taken == 0


@pytest.mark.django_db
def test_expired_only_after_registration_closed(auth_client, tenant_a):
    """EXPIRED terminal terkontrol: hanya setelah pendaftaran ditutup;
    dari RESERVED melepas kursi, dari DRAFT tidak."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a, capacity=5, deadline_in_days=10)
    a = _seed_pilgrim(tenant_a, "A")
    b = _seed_pilgrim(tenant_a, "B")
    reserved = _create(auth_client, dep, [a]).json()["id"]
    draft = _create(auth_client, dep, [b]).json()["id"]
    assert _transition(auth_client, reserved, BookingStatus.RESERVED).status_code == 200
    assert _dep(tenant_a, dep.pk).seats_taken == 1

    early = _transition(auth_client, reserved, BookingStatus.EXPIRED)
    assert early.status_code == 400
    assert "EXPIRED" in str(early.json())

    # tutup pendaftaran (deadline lewat)
    Departure.objects.without_tenant_guard().filter(pk=dep.pk).update(
        registration_deadline=timezone.localdate() - timedelta(days=1)
    )
    expired = _transition(auth_client, reserved, BookingStatus.EXPIRED)
    assert expired.status_code == 200
    assert expired.json()["status"] == BookingStatus.EXPIRED
    assert _dep(tenant_a, dep.pk).seats_taken == 0  # kursi dilepas
    assert all(p["participant_status"] == ParticipantStatus.CANCELED for p in expired.json()["participants"])

    # EXPIRED dari DRAFT (tanpa kursi) juga sah setelah pendaftaran ditutup
    expired_draft = _transition(auth_client, draft, BookingStatus.EXPIRED)
    assert expired_draft.status_code == 200
    assert _dep(tenant_a, dep.pk).seats_taken == 0
    # terminal
    assert _transition(auth_client, draft, BookingStatus.RESERVED).status_code == 400


@pytest.mark.django_db
def test_reserve_requires_open_and_seats(auth_client, tenant_a):
    """RESERVED dijaga: departure harus OPEN & kursi cukup (UAT-02
    berurutan)."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a, capacity=1)
    a = _seed_pilgrim(tenant_a, "A")
    b = _seed_pilgrim(tenant_a, "B")
    first = _create(auth_client, dep, [a]).json()["id"]
    second = _create(auth_client, dep, [b]).json()["id"]
    assert _transition(auth_client, first, BookingStatus.RESERVED).status_code == 200

    full = _transition(auth_client, second, BookingStatus.RESERVED)
    assert full.status_code == 400
    assert "seats" in full.json()["field_errors"]
    assert _dep(tenant_a, dep.pk).seats_taken == 1

    # departure ditutup setelah booking DRAFT dibuat → reserve ditolak
    Departure.objects.without_tenant_guard().filter(pk=dep.pk).update(
        status=DepartureStatus.READY
    )
    closed = _transition(auth_client, second, BookingStatus.RESERVED)
    assert closed.status_code == 400
    # tetap bisa dibatalkan
    assert _transition(auth_client, second, BookingStatus.CANCELED, "Tutup").status_code == 200


# ------------------------------------------------------ PATCH (draft-only) --


@pytest.mark.django_db
def test_patch_updates_draft_only(auth_client, tenant_a):
    """PATCH /bookings/{id}: notes/peserta/departure selama DRAFT (§8.3);
    peserta yang tidak berubah mempertahankan booking_passenger_id; kuota
    trial mengikuti delta; setelah RESERVED draft dibekukan."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a, capacity=10)
    other_dep = _seed_departure(tenant_a, capacity=10)
    a = _seed_pilgrim(tenant_a, "A")
    b = _seed_pilgrim(tenant_a, "B")
    c = _seed_pilgrim(tenant_a, "C")
    csrf = _csrf(auth_client)

    bid = _create(auth_client, dep, [a, b]).json()["id"]
    before = auth_client.get(f"/api/v1/bookings/{bid}").json()
    keep_passenger = next(p["booking_passenger_id"] for p in before["participants"] if p["pilgrim_name"] == "A")

    # notes saja
    r = auth_client.patch(
        f"/api/v1/bookings/{bid}", {"notes": "Bayar tunai"},
        content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
    )
    assert r.status_code == 200
    assert r.json()["notes"] == "Bayar tunai"

    # ganti peserta: A tetap (id permanen), B keluar, C masuk
    r = auth_client.patch(
        f"/api/v1/bookings/{bid}", {"participants": [str(a.pk), str(c.pk)]},
        content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
    )
    assert r.status_code == 200, r.content
    payload = r.json()
    assert payload["participant_count"] == 2
    names = {p["pilgrim_name"] for p in payload["participants"]}
    assert names == {"A", "C"}
    assert any(p["booking_passenger_id"] == keep_passenger for p in payload["participants"])
    assert payload["price_lines"][0]["qty"] == 2
    assert payload["total_amount"] == 90_000_000.0

    # ganti keberangkatan (masih DRAFT, guard dijalankan ulang)
    r = auth_client.patch(
        f"/api/v1/bookings/{bid}", {"departure": str(other_dep.pk)},
        content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
    )
    assert r.status_code == 200
    assert r.json()["departure_id"] == str(other_dep.pk)

    closed_dep = _seed_departure(tenant_a, status=DepartureStatus.DRAFT)
    bad = auth_client.patch(
        f"/api/v1/bookings/{bid}", {"departure": str(closed_dep.pk)},
        content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
    )
    assert bad.status_code == 400

    # setelah RESERVED, draft dibekukan
    assert _transition(auth_client, bid, BookingStatus.RESERVED).status_code == 200
    frozen = auth_client.patch(
        f"/api/v1/bookings/{bid}", {"notes": "tak boleh"},
        content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
    )
    assert frozen.status_code == 400
    assert "DRAFT" in str(frozen.json())

    # detail & list punya payload konsisten
    listed = auth_client.get("/api/v1/bookings").json()["results"]
    assert len(listed) == 1
    by_status = auth_client.get("/api/v1/bookings?status=RESERVED").json()["results"]
    assert len(by_status) == 1
    by_name = auth_client.get(f"/api/v1/bookings?q={payload['participants'][0]['pilgrim_name']}").json()["results"]
    assert len(by_name) == 1


# ------------------------------------------------------- kuota trial --


@pytest.mark.django_db
def test_trial_quota_per_jamaah_and_rollback(auth_client, tenant_a):
    """POL-08/§7.1.5: booking saat trial mengonsumsi kuota PER PESERTA
    (booking-jamaah); gagal → rollback; tidak pernah dikurangi."""
    _seed_env(tenant_a)
    pkg = _seed_package(tenant_a)
    dep = _seed_departure(tenant_a, package=pkg, capacity=30)
    p1, p2, p3 = (_seed_pilgrim(tenant_a, n) for n in ("P1", "P2", "P3"))
    trial = TenantTrial.objects.create(
        tenant=tenant_a,
        started_at=timezone.now(),
        ends_at=timezone.now() + timedelta(days=30),
        status=TrialStatus.RUNNING,
        dummy_count=18,
        config_snapshot_json={"dummy_booking_limit": 20},
    )

    # 3 peserta > sisa 2 → ditolak, counter & data tidak berubah (rollback)
    over = _create(auth_client, dep, [p1, p2, p3])
    assert over.status_code == 403
    assert over.json()["code"] == "TRIAL_QUOTA_EXCEEDED"
    trial.refresh_from_db()
    assert trial.dummy_count == 18
    assert Booking.objects.without_tenant_guard().filter(tenant=tenant_a).count() == 0

    # 2 peserta → tepat menghabiskan kuota
    ok = _create(auth_client, dep, [p1, p2])
    assert ok.status_code == 201
    trial.refresh_from_db()
    assert trial.dummy_count == 20

    # penuh → ditolak meski cuma 1 peserta
    last = _create(auth_client, dep, [p3])
    assert last.status_code == 403
    trial.refresh_from_db()
    assert trial.dummy_count == 20


@pytest.mark.django_db
def test_trial_quota_patch_delta_and_non_trial_passthrough(auth_client, tenant_a):
    """PATCH menambah peserta mengonsumsi delta; pengurangan tidak pernah
    mengembalikan kuota (TR03); tenant tanpa trial lolos tanpa cek."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a, capacity=30)
    a, b = (_seed_pilgrim(tenant_a, n) for n in ("A", "B"))
    trial = TenantTrial.objects.create(
        tenant=tenant_a,
        started_at=timezone.now(),
        ends_at=timezone.now() + timedelta(days=30),
        status=TrialStatus.RUNNING,
        dummy_count=19,
        config_snapshot_json={"dummy_booking_limit": 20},
    )
    csrf = _csrf(auth_client)

    bid = _create(auth_client, dep, [a]).json()["id"]  # 19 → 20 (penuh)
    trial.refresh_from_db()
    assert trial.dummy_count == 20

    # tambah 1 peserta saat kuota penuh → ditolak, data tak berubah
    over = auth_client.patch(
        f"/api/v1/bookings/{bid}", {"participants": [str(a.pk), str(b.pk)]},
        content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
    )
    assert over.status_code == 403
    assert over.json()["code"] == "TRIAL_QUOTA_EXCEEDED"
    trial.refresh_from_db()
    assert trial.dummy_count == 20
    assert BookingParticipant.objects.without_tenant_guard().filter(booking_id=bid).count() == 1

    # ganti komposisi (delta 0): B masuk, A keluar → lolos; kuota TIDAK kembali
    swap = auth_client.patch(
        f"/api/v1/bookings/{bid}", {"participants": [str(b.pk)]},
        content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
    )
    assert swap.status_code == 200
    trial.refresh_from_db()
    assert trial.dummy_count == 20  # TR03: tak pernah dikurangi

    # menambah A kembali (delta +1) tetap ditolak — bukti kuota tak kembali
    readd = auth_client.patch(
        f"/api/v1/bookings/{bid}", {"participants": [str(a.pk), str(b.pk)]},
        content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
    )
    assert readd.status_code == 403

    # tenant non-trial (tanpa record TenantTrial) lolos tanpa cek kuota
    other = Tenant.objects.create(slug="no-trial", legal_name="PT X", display_name="X")
    dep2 = _seed_departure(other, capacity=5)
    pg = _seed_pilgrim(other, "Solo")
    with _as_tenant(other):
        booking = create_booking(
            tenant=other,
            environment=Environment.DEMO,
            departure_id=dep2.pk,
            pilgrim_ids=[pg.pk],
        )
    assert booking.status == BookingStatus.DRAFT


# ----------------------------------------------------------- race (UAT-02) --


def _race_transition(tenant, booking_ids: list) -> list:
    """Jalankan transisi DRAFT→RESERVED serentak; hasil per thread."""
    results = [None] * len(booking_ids)
    barrier = Barrier(len(booking_ids))

    def worker(idx: int):
        try:
            token = set_current_tenant(tenant)
            try:
                barrier.wait(timeout=10)
                transition_booking(booking_id=booking_ids[idx], target=BookingStatus.RESERVED)
                results[idx] = "win"
            except DjangoValidationError:
                results[idx] = "lose"  # guard kursi penuh — kalah diserialisasi
            finally:
                clear_current_tenant(token)
        except Exception as exc:  # pragma: no cover — diagnostik kegagalan tak terduga
            results[idx] = exc
        finally:
            connection.close()

    workers = [Thread(target=worker, args=(i,)) for i in range(len(booking_ids))]
    for t in workers:
        t.start()
    for t in workers:
        t.join(timeout=30)
    return results


@pytest.mark.django_db(transaction=True)
def test_uat02_two_bookings_race_for_last_seat(db):
    """UAT-02 di level booking: dua staf serentak mengonfirmasi (RESERVED)
    dua booking untuk kursi terakhir → tepat satu menang; kursi tak lebih."""
    tenant = Tenant.objects.create(slug="race-bk", legal_name="PT Race BK", display_name="RaceBK")
    ids = []
    with _as_tenant(tenant):
        pkg = TravelPackage.objects.create(
            tenant=tenant, environment=Environment.DEMO, code="PKT-RACEBK", name="Race", price_idr=1000
        )
        dep = Departure.objects.create(
            tenant=tenant,
            environment=Environment.DEMO,
            code="DPR-RACEBK",
            package=pkg,
            start_at=timezone.now() + timedelta(days=30),
            city_of_origin="Jakarta",
            seat_capacity=1,
            status=DepartureStatus.OPEN,
        )
        for n in ("A", "B"):
            pilgrim = Pilgrim.objects.create(
                tenant=tenant, environment=Environment.DEMO,
                code=f"JM-RACE{n}", name=n,
            )
            booking = create_booking(
                tenant=tenant,
                environment=Environment.DEMO,
                departure_id=dep.pk,
                pilgrim_ids=[pilgrim.pk],
            )
            ids.append(booking.pk)

    results = _race_transition(tenant, ids)
    assert not any(isinstance(r, Exception) for r in results), results
    assert results.count("win") == 1, f"tepat satu pemenang, dapat: {results}"
    assert results.count("lose") == 1, f"tepat satu kalah, dapat: {results}"

    dep_row = Departure.objects.without_tenant_guard().get(pk=dep.pk)
    assert dep_row.seats_taken == 1  # tepat terisi, tidak overbooking
    statuses = sorted(
        Booking.objects.without_tenant_guard().filter(pk__in=ids).values_list("status", flat=True)
    )
    assert statuses == [BookingStatus.DRAFT, BookingStatus.RESERVED]


# ------------------------------------------- graph peserta §6.2 (unit) --


@pytest.mark.django_db
def test_participant_graph_six_two(db, tenant_a):
    """Graph §6.2: edge sah lolos, edge salah ditolak, terminal tertutup."""
    dep = _seed_departure(tenant_a, capacity=5)
    a = _seed_pilgrim(tenant_a, "A")
    with _as_tenant(tenant_a):
        booking = Booking.objects.create(
            tenant=tenant_a, environment=Environment.DEMO,
            code=generate_booking_code(), departure=dep,
        )
        row = BookingParticipant.objects.create(
            tenant=tenant_a, environment=Environment.DEMO,
            booking=booking, pilgrim=a,
        )

    with _as_tenant(tenant_a):
        # edge sah berantai
        advance_participant(participant=row, target=ParticipantStatus.REGISTERED)
        advance_participant(participant=row, target=ParticipantStatus.AWAITING_DP)
        advance_participant(participant=row, target=ParticipantStatus.DP_VERIFIED_PENDING_CHARGE)
        advance_participant(participant=row, target=ParticipantStatus.CONFIRMED)
        # lompatan ilegal ditolak (mis. CONFIRMED → REGISTERED)
        with pytest.raises(DjangoValidationError):
            advance_participant(participant=row, target=ParticipantStatus.REGISTERED)
        # REVIEW_REQUIRED → kembali ke jalur sah
        row.participant_status = ParticipantStatus.CONFIRMED
        row.save(update_fields=["participant_status", "updated_at"])
        advance_participant(participant=row, target=ParticipantStatus.REVIEW_REQUIRED)
        advance_participant(participant=row, target=ParticipantStatus.CANCELED)
        # terminal tertutup
        with pytest.raises(DjangoValidationError):
            advance_participant(participant=row, target=ParticipantStatus.REGISTERED)


# ------------------------------------------------------------ RBAC --


@pytest.mark.django_db
def test_rbac_booking_permission_matrix(client, tenant_a):
    """§8.3: Sales/Admin create+read; Ops read-only; Finance tanpa bookings.*."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a, capacity=10)
    a = _seed_pilgrim(tenant_a, "A")

    sales = _make_member(client, "sales-a@example.com", tenant_a, "Sales",
                         ["bookings.create", "bookings.read", "departures.read", "pilgrims.read"])
    created = _create(client, dep, [a])
    assert created.status_code == 201
    assert client.get("/api/v1/bookings").status_code == 200
    bid = created.json()["id"]
    assert _transition(client, bid, BookingStatus.RESERVED).status_code == 200

    ops = _make_member(client, "ops-a@example.com", tenant_a, "Operations",
                       ["bookings.read", "departures.read", "departures.manage"])
    assert client.get("/api/v1/bookings").status_code == 200
    assert client.get(f"/api/v1/bookings/{bid}").status_code == 200
    denied_create = _create(client, dep, [_seed_pilgrim(tenant_a, "B")])
    assert denied_create.status_code == 403
    assert _transition(client, bid, BookingStatus.CONFIRMED).status_code == 403

    finance = _make_member(client, "finance-a@example.com", tenant_a, "Finance",
                           ["payments.verify", "invoices.read", "packages.read"])
    assert client.get("/api/v1/bookings").status_code == 403
    assert client.get(f"/api/v1/bookings/{bid}").status_code == 403

    assert sales.is_active and ops.is_active and finance.is_active


# ------------------------------------------------- IDOR & environment --


@pytest.mark.django_db
def test_idor_cross_tenant_booking_404(auth_client, tenant_a, tenant_b, client):
    """Booking tenant_a tidak terlihat/diubah tenant_b (404, §2.2)."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a, capacity=5)
    a = _seed_pilgrim(tenant_a, "A")
    bid = _create(auth_client, dep, [a]).json()["id"]

    _make_member(client, "owner-b@example.com", tenant_b, "Owner", ["*"])
    assert client.get(f"/api/v1/bookings/{bid}").status_code == 404
    assert client.get("/api/v1/bookings").json()["results"] == []
    csrf = _csrf(client)
    assert client.patch(
        f"/api/v1/bookings/{bid}", {"notes": "hack"},
        content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
    ).status_code == 404
    assert _transition(client, bid, BookingStatus.RESERVED).status_code == 404


@pytest.mark.django_db
def test_readonly_environment_blocks_booking_writes(auth_client, tenant_a):
    """Environment read-only (§2.2, pasca-konversi) menolak semua tulisan."""
    _seed_env(tenant_a, state=EnvironmentState.READ_ONLY)
    dep = _seed_departure(tenant_a, capacity=5)
    a = _seed_pilgrim(tenant_a, "A")
    bid = _create(auth_client, dep, [a])
    assert bid.status_code == 403
    # baca tetap boleh
    assert auth_client.get("/api/v1/bookings").status_code == 200


# ------------------------------------------------------------ RLS --


@pytest.mark.django_db
@pytest.mark.parametrize(
    "table", ["booking_booking", "booking_bookingparticipant", "booking_bookingpriceline"]
)
def test_booking_tables_have_enforced_rls_policy(db, table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s",
            [table],
        )
        assert cursor.fetchone() == (True, True), f"{table} harus ENABLE+FORCE RLS (ADR-0003 §3)"
        cursor.execute(
            "SELECT qual, with_check FROM pg_policies WHERE tablename = %s", [table]
        )
        policy = cursor.fetchone()
        assert policy is not None
        for clause in policy:
            assert "current_setting('app.tenant_id'" in clause
            assert "NULLIF" in clause
