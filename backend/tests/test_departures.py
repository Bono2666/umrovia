"""S08 — Keberangkatan & seat atomik (exit gate S08: "Capacity concurrency
tests"; Spec §5.2, §6.5, §8.3, §10.1; PRD MOD-06, BR-002, UAT-01/UAT-02).

Membuktikan:
- CRUD keberangkatan: kode auto `DPR-`, validasi tanggal (§10.1), payload
  kursi (capacity/blocked/taken/available — formula MOD-06), ref paket
  lintas-environment ditolak (§5.2 integrity note);
- state machine §6.5: DRAFT→OPEN→READY→DEPARTED→COMPLETED atau CANCELED;
  transisi ilegal ditolak; alasan wajib saat cancel; setiap transisi jadi
  `departure_events` append-only + audit;
- **seat atomik (BR-002/UAT-02):** reserve/release ber-guard; dua pemesan
  serentak pada kursi terakhir → tepat satu menang; 10 thread pada 5 kursi →
  tepat 5 menang; invariant CHECK `taken + blocked <= capacity` di DB;
- guard invariant saat PATCH kapasitas/kursi blokir;
- isolasi lintas-tenant (404), RLS ENABLE+FORCE 2 tabel, RBAC §8.3
  (Ops tulis/kelola, Sales baca), guard environment (§2.2).
"""
from contextlib import contextmanager
from datetime import timedelta
from threading import Barrier, Thread

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from modules.audit.models import AuditEvent
from modules.catalog.models import TravelPackage
from modules.departures.models import Departure, DepartureEvent, DepartureStatus
from modules.departures.services import release_seats, reserve_seats
from modules.identity.models import User, UserStatus
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
        tenant=tenant,
        name=role_name,
        defaults={"permissions_json": perms},
    )
    TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant,
        user=member,
        role=role,
        status=MembershipStatus.ACTIVE,
    )
    client.force_login(member)
    return member


def _seed_package(tenant, environment: str = Environment.DEMO, code: str = "PKT-SEED001"):
    with _as_tenant(tenant):
        return TravelPackage.objects.create(
            tenant=tenant, environment=environment, code=code, name="Paket Seed"
        )


def _seed_departure(tenant, *, package=None, capacity=10, blocked=0, status=DepartureStatus.DRAFT,
                    environment=Environment.DEMO, code=None):
    if package is None:  # reuse paket seed bila sudah ada (hindari tabrakan kode)
        with _as_tenant(tenant):
            package = TravelPackage.objects.filter(environment=environment).first()
    if package is None:
        package = _seed_package(tenant, environment)
    with _as_tenant(tenant):
        return Departure.objects.create(
            tenant=tenant,
            environment=environment,
            code=code or f"DPR-{Departure.objects.without_tenant_guard().count() + 1:07d}",
            package=package,
            start_at=timezone.now() + timedelta(days=30),
            city_of_origin="Jakarta",
            seat_capacity=capacity,
            seats_blocked=blocked,
            status=status,
        )


# ------------------------------------------------------------------- CRUD --


@pytest.mark.django_db
def test_create_departure_payload_and_seat_math(auth_client, tenant_a):
    _seed_env(tenant_a)
    pkg = _seed_package(tenant_a)
    csrf = _csrf(auth_client)
    response = auth_client.post(
        "/api/v1/departures",
        {
            "package": str(pkg.pk),
            "start_at": (timezone.now() + timedelta(days=45)).isoformat(),
            "city_of_origin": "Jakarta",
            "seat_capacity": 20,
            "seats_blocked": 3,
        },
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 201, response.content
    payload = response.json()
    assert payload["code"].startswith("DPR-")
    assert payload["environment"] == Environment.DEMO  # trial → demo
    assert payload["status"] == "DRAFT"
    assert payload["seat_capacity"] == 20
    assert payload["seats_blocked"] == 3
    assert payload["seats_taken"] == 0
    assert payload["available_seats"] == 17  # kapasitas − terpakai − terblokir (MOD-06)
    assert payload["package_code"] == pkg.code

    # seats_taken tidak pernah bisa dipasok lewat input API (hanya layanan atomik)
    tampered = auth_client.post(
        "/api/v1/departures",
        {
            "package": str(pkg.pk),
            "start_at": (timezone.now() + timedelta(days=46)).isoformat(),
            "city_of_origin": "Jakarta",
            "seat_capacity": 5,
            "seats_taken": 99,
        },
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert tampered.status_code == 201
    assert tampered.json()["seats_taken"] == 0

    events = AuditEvent.objects.filter(action="departures.created", tenant=tenant_a)
    assert any(e.changes_json.get("seat_capacity") == 20 for e in events)


@pytest.mark.django_db
def test_departure_validation_rules(auth_client, tenant_a):
    _seed_env(tenant_a)
    pkg = _seed_package(tenant_a)
    csrf = _csrf(auth_client)
    start = (timezone.now() + timedelta(days=45)).isoformat()

    # kepulangan sebelum keberangkatan (§10.1)
    bad_end = auth_client.post(
        "/api/v1/departures",
        {"package": str(pkg.pk), "start_at": start,
         "end_at": (timezone.now() + timedelta(days=40)).isoformat(),
         "city_of_origin": "Jakarta", "seat_capacity": 10},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert bad_end.status_code == 400

    # batas pendaftaran setelah tanggal terbang
    bad_deadline = auth_client.post(
        "/api/v1/departures",
        {"package": str(pkg.pk), "start_at": start,
         "registration_deadline": (timezone.now() + timedelta(days=60)).date().isoformat(),
         "city_of_origin": "Jakarta", "seat_capacity": 10},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert bad_deadline.status_code == 400

    # kota asal wajib
    no_city = auth_client.post(
        "/api/v1/departures",
        {"package": str(pkg.pk), "start_at": start, "city_of_origin": "  ", "seat_capacity": 10},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert no_city.status_code == 400


@pytest.mark.django_db
def test_departure_rejects_cross_environment_package(auth_client, tenant_a):
    _seed_env(tenant_a, Environment.DEMO, EnvironmentState.READ_ONLY)  # pasca-konversi
    _seed_env(tenant_a, Environment.PRODUCTION, EnvironmentState.ACTIVE)
    demo_pkg = _seed_package(tenant_a, Environment.DEMO)
    csrf = _csrf(auth_client)
    response = auth_client.post(
        "/api/v1/departures",
        {
            "package": str(demo_pkg.pk),
            "start_at": (timezone.now() + timedelta(days=45)).isoformat(),
            "city_of_origin": "Jakarta",
            "seat_capacity": 10,
        },
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 400  # referensi lintas-environment ditolak (§5.2)


@pytest.mark.django_db
def test_departure_list_filters_and_idor(auth_client, tenant_a, tenant_b):
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a, status=DepartureStatus.OPEN)
    _seed_departure(tenant_a, code="DPR-0000002", status=DepartureStatus.DRAFT)

    listed = auth_client.get("/api/v1/departures").json()["results"]
    assert len(listed) == 2
    by_status = auth_client.get("/api/v1/departures?status=OPEN").json()["results"]
    assert len(by_status) == 1 and by_status[0]["code"] == dep.code
    by_pkg = auth_client.get(f"/api/v1/departures?package={dep.package_id}").json()["results"]
    assert len(by_pkg) == 2
    by_q = auth_client.get("/api/v1/departures?q=jakarta").json()["results"]
    assert len(by_q) == 2

    foreign = _seed_departure(tenant_b, code="DPR-FOREIGN")
    csrf = _csrf(auth_client)
    assert auth_client.get(f"/api/v1/departures/{foreign.pk}").status_code == 404
    patched = auth_client.patch(
        f"/api/v1/departures/{foreign.pk}",
        {"city_of_origin": "Hack"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert patched.status_code == 404
    transitioned = auth_client.post(
        f"/api/v1/departures/{foreign.pk}/transition",
        {"target": "OPEN"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert transitioned.status_code == 404


# ------------------------------------------------- state machine (§6.5) --


def _transition(client, departure_id, target, reason=None, csrf=None):
    body = {"target": target}
    if reason is not None:
        body["reason"] = reason
    return client.post(
        f"/api/v1/departures/{departure_id}/transition",
        body,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


@pytest.mark.django_db
def test_departure_happy_path_transition_writes_events(auth_client, tenant_a):
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a, capacity=40)
    csrf = _csrf(auth_client)

    for target in ("OPEN", "READY", "DEPARTED", "COMPLETED"):
        response = _transition(auth_client, dep.pk, target, csrf=csrf)
        assert response.status_code == 200, (target, response.content)
        assert response.json()["status"] == target

    events = list(DepartureEvent.objects.without_tenant_guard().filter(departure=dep))
    assert [(e.prior_status, e.next_status) for e in reversed(events)] == [
        ("DRAFT", "OPEN"),
        ("OPEN", "READY"),
        ("READY", "DEPARTED"),
        ("DEPARTED", "COMPLETED"),
    ]
    audits = AuditEvent.objects.filter(action="departures.transitioned").count()
    assert audits == 4


@pytest.mark.django_db
def test_departure_illegal_transitions_rejected(auth_client, tenant_a):
    _seed_env(tenant_a)
    csrf = _csrf(auth_client)

    draft = _seed_departure(tenant_a, code="DPR-0000010")
    assert _transition(auth_client, draft.pk, "DEPARTED", csrf=csrf).status_code == 400  # lompat stage
    assert _transition(auth_client, draft.pk, "OPEN", csrf=csrf).status_code == 200
    assert _transition(auth_client, draft.pk, "OPEN", csrf=csrf).status_code == 400  # idem-target

    open_dep = draft
    assert _transition(auth_client, open_dep.pk, "COMPLETED", csrf=csrf).status_code == 400
    assert _transition(auth_client, open_dep.pk, "CANCELED", reason="", csrf=csrf).status_code == 400  # alasan wajib
    canceled = _transition(auth_client, open_dep.pk, "CANCELED", reason=" Visa ditolak", csrf=csrf)
    assert canceled.status_code == 200
    assert _transition(auth_client, open_dep.pk, "OPEN", csrf=csrf).status_code == 400  # terminal


@pytest.mark.django_db
def test_departure_cancel_requires_reason_and_appends_event(auth_client, tenant_a):
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a, status=DepartureStatus.OPEN)
    csrf = _csrf(auth_client)
    no_reason = _transition(auth_client, dep.pk, "CANCELED", csrf=csrf)
    assert no_reason.status_code == 400

    canceled = _transition(auth_client, dep.pk, "CANCELED", reason="Visa ditolak KBIH", csrf=csrf)
    assert canceled.status_code == 200
    event = DepartureEvent.objects.without_tenant_guard().get(departure=dep)
    assert event.prior_status == "OPEN" and event.next_status == "CANCELED"
    assert event.reason == "Visa ditolak KBIH"
    audit = AuditEvent.objects.get(action="departures.transitioned")
    assert audit.changes_json["transition"] == ["OPEN", "CANCELED"]


@pytest.mark.django_db
def test_departure_open_requires_capacity(auth_client, tenant_a):
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a, capacity=0)
    csrf = _csrf(auth_client)
    assert _transition(auth_client, dep.pk, "OPEN", csrf=csrf).status_code == 400


@pytest.mark.django_db
def test_departure_events_are_append_only(db):
    dep_event = DepartureEvent(
        tenant=None,  # tidak disimpan — hanya uji guard save/delete
        environment=Environment.DEMO,
        prior_status="A",
        next_status="B",
    )
    dep_event._state.adding = False  # dipaksa dianggap update
    with pytest.raises(DjangoValidationError):
        dep_event.save()


# ------------------------------------------------------- seat atomik --


@pytest.mark.django_db
def test_reserve_until_full_then_release(auth_client, tenant_a):
    dep = _seed_departure(tenant_a, capacity=3, blocked=1)

    with _as_tenant(tenant_a):
        assert reserve_seats(dep.pk, 1) is True
        assert reserve_seats(dep.pk, 1) is True
        assert reserve_seats(dep.pk, 1) is False  # kapasitas 3 − blokir 1 → sisa 1
        dep.refresh_from_db()
        assert dep.seats_taken == 2
        assert dep.available_seats == 0

        assert release_seats(dep.pk, 2) is True
        dep.refresh_from_db()
        assert dep.seats_taken == 0
        assert release_seats(dep.pk, 1) is False  # over-release ditolak guard

        with pytest.raises(DjangoValidationError):
            reserve_seats(dep.pk, 0)  # count < 1


@pytest.mark.django_db
def test_patch_seat_fields_guard_invariant(auth_client, tenant_a):
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a, capacity=10)
    with _as_tenant(tenant_a):
        assert reserve_seats(dep.pk, 8)
    csrf = _csrf(auth_client)

    # kuota blokir menaikkan di atas sisa → 400 (BR-002)
    bad_block = auth_client.patch(
        f"/api/v1/departures/{dep.pk}",
        {"seats_blocked": 3},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert bad_block.status_code == 400

    # kapasitas diturunkan di bawah terpakai → 400
    bad_capacity = auth_client.patch(
        f"/api/v1/departures/{dep.pk}",
        {"seat_capacity": 5},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert bad_capacity.status_code == 400

    # pengecilan melewati validasi aplikasi → CHECK DB menangkap (pengaman kedua)
    with pytest.raises(IntegrityError), transaction.atomic():
        Departure.objects.without_tenant_guard().filter(pk=dep.pk).update(seat_capacity=2)

    # kenaikan kapasitas aman
    ok = auth_client.patch(
        f"/api/v1/departures/{dep.pk}",
        {"seat_capacity": 12},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert ok.status_code == 200
    assert ok.json()["available_seats"] == 4  # 12 − 8 terpakai − 0 blokir


def _race(tenant, departure_id, threads: int) -> list:
    """Jalankan `threads` pemesan serentak; hasil per thread (True/False)."""
    results = [None] * threads
    barrier = Barrier(threads)

    def worker(idx: int):
        try:
            token = set_current_tenant(tenant)
            try:
                barrier.wait(timeout=10)
                results[idx] = reserve_seats(departure_id, 1)
            finally:
                clear_current_tenant(token)
        except Exception as exc:  # pragma: no cover — diagnostik kegagalan tak terduga
            results[idx] = exc
        finally:
            connection.close()  # koneksi thread ditutup agar tidak menggantung

    workers = [Thread(target=worker, args=(i,)) for i in range(threads)]
    for t in workers:
        t.start()
    for t in workers:
        t.join(timeout=30)
    return results


@pytest.mark.django_db(transaction=True)
def test_uat02_two_staff_race_for_last_seat(db):
    """UAT-02: dua petugas serentak mengambil kursi terakhir → tepat satu sukses."""
    tenant = Tenant.objects.create(slug="race-1", legal_name="PT Race", display_name="Race")
    dep_pk = None
    with _as_tenant(tenant):
        pkg = TravelPackage.objects.create(
            tenant=tenant, environment=Environment.DEMO, code="PKT-RACE01", name="Race"
        )
        dep = Departure.objects.create(
            tenant=tenant,
            environment=Environment.DEMO,
            code="DPR-RACE01",
            package=pkg,
            start_at=timezone.now() + timedelta(days=30),
            city_of_origin="Jakarta",
            seat_capacity=1,
        )
        dep_pk = dep.pk

    results = _race(tenant, dep_pk, threads=2)
    assert not any(isinstance(r, Exception) for r in results), results
    assert results.count(True) == 1, f"tepat satu pemenang, dapat: {results}"

    dep = Departure.objects.without_tenant_guard().get(pk=dep_pk)
    assert dep.seats_taken == 1  # kapasitas terisi tepat, tidak overbooking


@pytest.mark.django_db(transaction=True)
def test_concurrent_reserve_never_overbooks(db):
    """10 thread berebut 5 kursi (kapasitas 5) → tepat 5 sukses, tak lebih."""
    tenant = Tenant.objects.create(slug="race-2", legal_name="PT Race2", display_name="Race2")
    with _as_tenant(tenant):
        pkg = TravelPackage.objects.create(
            tenant=tenant, environment=Environment.DEMO, code="PKT-RACE02", name="Race2"
        )
        dep = Departure.objects.create(
            tenant=tenant,
            environment=Environment.DEMO,
            code="DPR-RACE02",
            package=pkg,
            start_at=timezone.now() + timedelta(days=30),
            city_of_origin="Jakarta",
            seat_capacity=5,
        )
        dep_pk = dep.pk

    results = _race(tenant, dep_pk, threads=10)
    assert not any(isinstance(r, Exception) for r in results), results
    assert results.count(True) == 5, f"tepat 5 pemenang, dapat: {results}"

    dep = Departure.objects.without_tenant_guard().get(pk=dep_pk)
    assert dep.seats_taken == 5
    assert dep.available_seats == 0


# ------------------------------------------------------------------ RBAC --


@pytest.mark.django_db
def test_departure_rbac_matrix(client, db, user, owner_a, tenant_a):
    _seed_env(tenant_a)
    pkg = _seed_package(tenant_a)
    csrf = _csrf(client)

    # Sales: baca ✓ tulis ✗ transisi ✗ (§8.3 departures = Ops/Admin)
    _make_member(client, "sales@example.com", tenant_a, "Sales", ["packages.read", "departures.read"])
    assert client.get("/api/v1/departures").status_code == 200
    denied = client.post(
        "/api/v1/departures",
        {"package": str(pkg.pk), "start_at": (timezone.now() + timedelta(days=30)).isoformat(),
         "city_of_origin": "Jakarta", "seat_capacity": 5},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert denied.status_code == 403

    # Operations: tulis ✓ transisi ✓
    _make_member(
        client,
        "ops@example.com",
        tenant_a,
        "Operations",
        ["packages.read", "packages.write", "departures.read", "departures.write", "departures.manage"],
    )
    csrf = _csrf(client)
    created = client.post(
        "/api/v1/departures",
        {"package": str(pkg.pk), "start_at": (timezone.now() + timedelta(days=31)).isoformat(),
         "city_of_origin": "Jakarta", "seat_capacity": 5},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert created.status_code == 201
    transitioned = _transition(client, created.json()["id"], "OPEN", csrf=csrf)
    assert transitioned.status_code == 200
    assert AuditEvent.objects.filter(action="departures.transitioned").exists()

    # Sales mencoba transisi → 403 (tanpa departures.manage)
    _make_member(client, "sales2@example.com", tenant_a, "Sales", ["departures.read"])
    csrf = _csrf(client)
    denied_transition = _transition(client, created.json()["id"], "READY", csrf=csrf)
    assert denied_transition.status_code == 403


@pytest.mark.django_db
def test_departure_write_denied_in_read_only_environment(auth_client, tenant_a):
    _seed_env(tenant_a, Environment.DEMO, EnvironmentState.READ_ONLY)  # pasca-konversi
    _seed_env(tenant_a, Environment.PRODUCTION, EnvironmentState.ACTIVE)
    demo_dep = _seed_departure(tenant_a, environment=Environment.DEMO)
    csrf = _csrf(auth_client)

    patched = auth_client.patch(
        f"/api/v1/departures/{demo_dep.pk}",
        {"city_of_origin": "Bandung"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert patched.status_code == 403  # §2.2 demo read-only
    transitioned = _transition(auth_client, demo_dep.pk, "OPEN", csrf=csrf)
    assert transitioned.status_code == 403
    assert auth_client.get(f"/api/v1/departures/{demo_dep.pk}").status_code == 200  # tetap terbaca


# ------------------------------------------------------------- RLS (§5.6) --


@pytest.mark.django_db
@pytest.mark.parametrize("table", ["departures_departure", "departures_departureevent"])
def test_departure_tables_have_enforced_rls_policy(db, table):
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
