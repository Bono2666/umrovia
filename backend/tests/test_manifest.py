"""S10 — Manifest base & checklist operasional (exit gate S10: "Basic
departure manifests export"; Spec §5.2/§6.5/§7.6/§8.3/UI-11/UI-12;
PRD MOD-08/MOD-12, OPS-02/OPS-03, UAT-14).

Membuktikan:
- CRUD `document_requirements` (UI-11): global vs per-paket, override per
  `kind`, duplikat per lingkup ditolak, RBAC `documents.requirements.manage`
  (Ops/Admin/Owner), environment read-only menolak tulis (§2.2);
- gerbang §6.5 yang diisi S10: `READY` ditolak saat dokumen wajib
  `before_ready` belum APPROVED (OPS-02: tanpa exception), lolos dengan
  *approved exception* `checklist_exception` + alasan wajib + jejak audit;
  `DEPARTED` dijaga requirement `before_departure`; booking
  `READY_TO_DEPART` dijaga `documents_complete`; tanpa requirement → lulus;
- `GET /departures/{id}/manifest` (§8.3/UI-12): hanya peserta booking AKTIF
  departure itu (UAT-14), field selalu masked (§10.1), filter MOD-12
  (q/status dokumen), RBAC Ops/Admin/Owner (Sales/Finance 403), IDOR 404;
- `POST .../manifest/publish` (§7.6): versi bernomor urut unik + snapshot
  JSON di storage + checksum sha256 + audit; environment read-only 403;
- ekspor CSV (exit gate): BOM UTF-8, prefiks DEMO- (§7.2), hanya
  keberangkatan itu; `pii=1` tanpa `manifest.export_pii` → 403 DAN audit
  `manifest.export_denied` (OPS-03); Owner → nilai mentah + audit
  `manifest.exported` dengan flag PII;
- RBAC default §3: Admin/Ops dapat read/publish/export + requirements.manage,
  `manifest.export_pii` HANYA Owner (Admin/Ops = S → tidak di-grant v1);
- RLS ENABLE+FORCE + policy tenant pada 2 tabel (§5.6, ADR-0003 §3).
"""
import hashlib
import json
from contextlib import contextmanager
from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.utils import timezone

from modules.audit.models import AuditEvent
from modules.booking.models import Booking, BookingStatus
from modules.catalog.models import TravelPackage
from modules.departures.models import Departure, DepartureEvent, DepartureStatus
from modules.identity.models import User, UserStatus
from modules.manifest.models import DocumentRequirement, ManifestVersion
from modules.manifest.services import effective_requirements
from modules.pilgrims.crypto import encrypt_pii
from modules.pilgrims.models import Pilgrim, PilgrimDocument
from modules.tenants.context import clear_current_tenant, set_current_tenant
from modules.tenants.models import (
    Environment,
    EnvironmentState,
    MembershipStatus,
    Role,
    TenantEnvironment,
    TenantMembership,
)
from modules.tenants.rbac import DEFAULT_ROLE_PERMISSIONS


@contextmanager
def _as_tenant(tenant):
    token = set_current_tenant(tenant)
    try:
        yield
    finally:
        clear_current_tenant(token)


@pytest.fixture
def media_root(settings, tmp_path):
    """Snapshot publish ditulis ke MEDIA_ROOT sementara — tidak menyentuh repo."""
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


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


def _seed_package(tenant, *, code: str | None = None) -> TravelPackage:
    with _as_tenant(tenant):
        return TravelPackage.objects.create(
            tenant=tenant,
            environment=Environment.DEMO,
            code=code or f"PKT-{uuid4().hex[:8].upper()}",
            name="Paket Umroh",
            price_idr=45_000_000,
        )


def _seed_departure(
    tenant,
    *,
    package: TravelPackage | None = None,
    capacity: int = 10,
    status: str = DepartureStatus.OPEN,
) -> Departure:
    if package is None:
        package = _seed_package(tenant)
    with _as_tenant(tenant):
        return Departure.objects.create(
            tenant=tenant,
            environment=Environment.DEMO,
            code=f"DPR-{uuid4().hex[:8].upper()}",
            package=package,
            start_at=timezone.now() + timedelta(days=30),
            city_of_origin="Jakarta",
            seat_capacity=capacity,
            status=status,
        )


def _seed_pilgrim(tenant, name: str, **extra) -> Pilgrim:
    with _as_tenant(tenant):
        return Pilgrim.objects.create(
            tenant=tenant,
            environment=Environment.DEMO,
            code=f"JM-{uuid4().hex[:8].upper()}",
            name=name,
            **extra,
        )


def _pilgrim_by_name(tenant, name) -> Pilgrim:
    with _as_tenant(tenant):
        return Pilgrim.objects.get(name=name)


def _requirement(
    tenant,
    *,
    kind: str = "ktp",
    package: TravelPackage | None = None,
    mandatory: bool = True,
    deadline_rule: str = "before_ready",
) -> DocumentRequirement:
    with _as_tenant(tenant):
        return DocumentRequirement.objects.create(
            tenant=tenant,
            environment=Environment.DEMO,
            package=package,
            kind=kind,
            mandatory=mandatory,
            deadline_rule=deadline_rule,
        )


def _approve_doc(tenant, pilgrim: Pilgrim, kind: str, *, version: int = 1, status: str = "APPROVED"):
    """Dokumen versi `version` langsung via ORM (jalur review API = S07)."""
    with _as_tenant(tenant):
        return PilgrimDocument.objects.create(
            tenant=tenant,
            environment=Environment.DEMO,
            pilgrim=pilgrim,
            kind=kind,
            object_key=f"{tenant.id}/demo/{pilgrim.code}/{kind}-v{version}.pdf",
            version=version,
            status=status,
        )


def _create_booking(client, departure, pilgrims, **extra) -> dict:
    csrf = _csrf(client)
    body = {
        "departure": str(departure.pk),
        "participants": [str(getattr(p, "pk", p)) for p in pilgrims],
        **extra,
    }
    response = client.post(
        "/api/v1/bookings", body, content_type="application/json", HTTP_X_CSRFTOKEN=csrf
    )
    assert response.status_code == 201, response.content
    return response.json()


def _transition_booking(client, booking_id, target: str, reason: str = "") -> dict:
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


def _transition_departure(client, departure_id, target: str, **extra) -> dict:
    csrf = _csrf(client)
    return client.post(
        f"/api/v1/departures/{departure_id}/transition",
        {"target": target, **extra},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )


def _manifest(client, departure_id, query: str = "") -> dict:
    return client.get(f"/api/v1/departures/{departure_id}/manifest{query}")


def _csv(client, departure_id, query: str = ""):
    """Ekspor CSV → response penuh (status, body, header Content-Disposition)."""
    return client.get(f"/api/v1/departures/{departure_id}/manifest/export{query}")


# ------------------------------------- document_requirements (UI-11) --


@pytest.mark.django_db
def test_requirement_crud_override_and_uniqueness(auth_client, tenant_a):
    """CRUD checklist: global vs per-paket, duplikat per lingkup ditolak,
    override per-kind oleh spesifik paket (MOD-08)."""
    _seed_env(tenant_a)
    pkg = _seed_package(tenant_a)

    csrf = _csrf(auth_client)
    create = auth_client.post(
        "/api/v1/document-requirements",
        {"kind": "ktp", "mandatory": True, "deadline_rule": "before_ready"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert create.status_code == 201, create.content
    payload = create.json()
    assert payload["package_id"] is None and payload["kind"] == "ktp"

    dup = auth_client.post(
        "/api/v1/document-requirements",
        {"kind": "ktp"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert dup.status_code == 400  # uq_docreq_global_kind

    scoped = auth_client.post(
        "/api/v1/document-requirements",
        {"package": str(pkg.pk), "kind": "ktp", "mandatory": False},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert scoped.status_code == 201  # lingkup berbeda → sah (uq per paket)

    listing = auth_client.get("/api/v1/document-requirements")
    assert listing.status_code == 200 and len(listing.json()) == 2

    # override: paket memakai barisnya sendiri — global kena timpa per-kind
    with _as_tenant(tenant_a):
        effective = {r.kind: r for r in effective_requirements(pkg)}
        assert effective["ktp"].package_id == pkg.pk
        assert effective["ktp"].mandatory is False

    detail_id = scoped.json()["id"]
    patched = auth_client.patch(
        f"/api/v1/document-requirements/{detail_id}",
        {"mandatory": True},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert patched.status_code == 200 and patched.json()["mandatory"] is True

    deleted = auth_client.delete(
        f"/api/v1/document-requirements/{detail_id}", HTTP_X_CSRFTOKEN=csrf
    )
    assert deleted.status_code == 204
    with _as_tenant(tenant_a):
        effective = {r.kind: r for r in effective_requirements(pkg)}
        assert effective["ktp"].package_id is None  # kembali ke global


@pytest.mark.django_db
def test_requirement_rbac_default_grants(tenant_a):
    """`documents.requirements.manage`: Operations (grant default) boleh
    tulis; Sales (grant default) 403 membaca maupun menulis."""
    _seed_env(tenant_a)
    pkg = _seed_package(tenant_a)

    ops = Client()
    _make_member(ops, "ops10@example.com", tenant_a, "Operations",
                 DEFAULT_ROLE_PERMISSIONS["Operations"])
    ok = ops.post(
        "/api/v1/document-requirements",
        {"package": str(pkg.pk), "kind": "passport"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=_csrf(ops),
    )
    assert ok.status_code == 201

    sales = Client()
    _make_member(sales, "sales10@example.com", tenant_a, "Sales",
                 DEFAULT_ROLE_PERMISSIONS["Sales"])
    assert sales.get("/api/v1/document-requirements").status_code == 403
    assert sales.post(
        "/api/v1/document-requirements",
        {"kind": "kk"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=_csrf(sales),
    ).status_code == 403


@pytest.mark.django_db
def test_requirement_readonly_env_denied(auth_client, tenant_a):
    """Environment demo → READ_ONLY (pasca-konversi) menolak tulisan checklist."""
    _seed_env(tenant_a, state=EnvironmentState.READ_ONLY)
    response = auth_client.post(
        "/api/v1/document-requirements",
        {"kind": "ktp"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=_csrf(auth_client),
    )
    assert response.status_code == 403
    assert auth_client.get("/api/v1/document-requirements").status_code == 200  # baca OK


def test_default_role_grants_follow_permission_matrix():
    """Matriks §3: Admin/Ops dapat manifest read/publish/export + kelola
    checklist; `manifest.export_pii` HANYA Owner (Admin/Ops = S → v1 tidak)."""
    admin = DEFAULT_ROLE_PERMISSIONS["Admin"]
    ops = DEFAULT_ROLE_PERMISSIONS["Operations"]
    for perm in ("manifest.read", "manifest.publish", "manifest.export",
                 "documents.requirements.manage"):
        assert perm in admin, perm
        assert perm in ops, perm
    for role in ("Admin", "Sales", "Finance", "Operations", "Document Reviewer"):
        assert "manifest.export_pii" not in DEFAULT_ROLE_PERMISSIONS[role]
    assert "*" in DEFAULT_ROLE_PERMISSIONS["Owner"]  # Owner = wildcard
    for perm in ("manifest.read", "manifest.publish", "manifest.export"):
        assert perm not in DEFAULT_ROLE_PERMISSIONS["Sales"]
        assert perm not in DEFAULT_ROLE_PERMISSIONS["Finance"]


# ------------------------------------------- gerbang checklist §6.5 --


@pytest.mark.django_db
def test_departure_ready_gate_blocks_until_docs_approved(auth_client, tenant_a):
    """OPS-02: READY ditolak bila dokumen wajib belum lengkap; lolos setelah
    semua peserta punya dokumen ber-APPROVED; tanpa requirement → lulus."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a)
    budi = _seed_pilgrim(tenant_a, "Budi Santoso")
    booking = _create_booking(auth_client, dep, [budi])

    # tanpa requirement apa pun → gerbang longgar (hook S08 vacuous)
    ok = _transition_departure(auth_client, dep.pk, "READY")
    assert ok.status_code == 200 and ok.json()["status"] == DepartureStatus.READY
    assert booking["status"] == BookingStatus.DRAFT

    # departure kedua: requirement aktif, dokumen belum ada → ditolak
    _requirement(tenant_a, kind="ktp")
    dep2 = _seed_departure(tenant_a)
    sari = _seed_pilgrim(tenant_a, "Sari")
    _create_booking(auth_client, dep2, [sari])

    blocked = _transition_departure(auth_client, dep2.pk, "READY")
    assert blocked.status_code == 400
    assert "checklist" in blocked.json()["field_errors"]
    reason = blocked.json()["field_errors"]["checklist"][0]
    assert "belum diunggah" in reason

    _approve_doc(tenant_a, sari, "ktp")
    passed = _transition_departure(auth_client, dep2.pk, "READY")
    assert passed.status_code == 200 and passed.json()["status"] == DepartureStatus.READY


@pytest.mark.django_db
def test_departure_ready_gate_mandatory_flag_respected(auth_client, tenant_a):
    """Requirement `mandatory=False` tidak menggerakkan gerbang."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a)
    p = _seed_pilgrim(tenant_a, "Tono")
    _create_booking(auth_client, dep, [p])
    _requirement(tenant_a, kind="passport", mandatory=False)

    response = _transition_departure(auth_client, dep.pk, "READY")
    assert response.status_code == 200


@pytest.mark.django_db
def test_departure_ready_approved_exception_audited(auth_client, tenant_a):
    """§6.5 *approved exception* (OPS-02): `checklist_exception` wajib alasan,
    tercatat di departure_events + audit; tanpa exception tetap ditolak."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a)
    p = _seed_pilgrim(tenant_a, "Aminah")
    _create_booking(auth_client, dep, [p])
    _requirement(tenant_a, kind="ktp")

    plain = _transition_departure(auth_client, dep.pk, "READY")
    assert plain.status_code == 400  # tanpa exception → ditolak

    no_reason = _transition_departure(auth_client, dep.pk, "READY", checklist_exception=True)
    assert no_reason.status_code == 400
    assert "reason" in no_reason.json()["field_errors"]

    with_reason = _transition_departure(
        auth_client,
        dep.pk,
        "READY",
        checklist_exception=True,
        reason="Dokumen tertunda di kantor imigrasi — disetujui Ops Manager",
    )
    assert with_reason.status_code == 200

    with _as_tenant(tenant_a):
        event = DepartureEvent.objects.filter(departure=dep).order_by("-created_at").first()
        assert event.next_status == DepartureStatus.READY
        assert "disetujui Ops Manager" in event.reason
    audit = AuditEvent.objects.filter(action="departures.transitioned").first()
    assert audit is not None and audit.changes_json.get("checklist_exception") is True


@pytest.mark.django_db
def test_departure_departed_gate_before_departure(auth_client, tenant_a):
    """Requirement `before_departure` menjaga READY → DEPARTED (strict)."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a)  # OPEN → booking → READY → coba DEPARTED
    p = _seed_pilgrim(tenant_a, "Hasan")
    _create_booking(auth_client, dep, [p])
    _requirement(tenant_a, kind="passport", deadline_rule="before_departure")
    assert _transition_departure(auth_client, dep.pk, "READY").status_code == 200
    # gerbang before_ready longgar — hanya before_departure yang berlaku di sini

    blocked = _transition_departure(auth_client, dep.pk, "DEPARTED")
    assert blocked.status_code == 400
    assert "checklist" in blocked.json()["field_errors"]

    _approve_doc(tenant_a, p, "passport")
    ok = _transition_departure(auth_client, dep.pk, "DEPARTED")
    assert ok.status_code == 200 and ok.json()["status"] == DepartureStatus.DEPARTED


@pytest.mark.django_db
def test_booking_ready_to_depart_documents_gate(auth_client, tenant_a, settle_demo_dp):
    """Hook S09 `documents_complete` terisi: booking → READY_TO_DEPART ditolak
    sampai dokumen wajib peserta APPROVED (PRD "checklist per jamaah")."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a)
    p = _seed_pilgrim(tenant_a, "Rina")
    booking = _create_booking(auth_client, dep, [p])
    _requirement(tenant_a, kind="ktp")

    assert _transition_booking(auth_client, booking["id"], "RESERVED").status_code == 200
    settle_demo_dp(auth_client, booking["id"])
    assert _transition_booking(auth_client, booking["id"], "CONFIRMED").status_code == 200
    assert _transition_booking(auth_client, booking["id"], "DOCUMENT_PROCESS").status_code == 200

    blocked = _transition_booking(auth_client, booking["id"], "READY_TO_DEPART")
    assert blocked.status_code == 400
    assert "checklist" in blocked.json()["field_errors"]

    _approve_doc(tenant_a, p, "ktp")
    ok = _transition_booking(auth_client, booking["id"], "READY_TO_DEPART")
    assert ok.status_code == 200 and ok.json()["status"] == BookingStatus.READY_TO_DEPART


# ------------------------------------------------- manifest (UI-12) --


def _seed_roster(auth_client, tenant_a, departure) -> None:
    """1 booking aktif (2 peserta: satu lengkap, satu tidak) + 1 CANCELED +
    1 EXPIRED — yang terminal tidak boleh muncul di manifest."""
    done = _seed_pilgrim(tenant_a, "Sari Wijaya")
    missing = _seed_pilgrim(tenant_a, "Asep Nugraha")
    canceled_p = _seed_pilgrim(tenant_a, "Budi Batal")
    expired_p = _seed_pilgrim(tenant_a, "Tuti Expired")

    _create_booking(auth_client, departure, [done, missing])
    canceled = _create_booking(auth_client, departure, [canceled_p])
    expired = _create_booking(auth_client, departure, [expired_p])
    for bid, status in (
        (canceled["id"], BookingStatus.CANCELED),
        (expired["id"], BookingStatus.EXPIRED),
    ):
        with _as_tenant(tenant_a):
            booking = Booking.objects.get(pk=bid)
            booking.status = status
            booking.save(update_fields=["status", "updated_at"])


@pytest.mark.django_db
def test_manifest_get_rows_filters_and_masking(auth_client, tenant_a):
    """Roster manifest: hanya peserta booking aktif (UAT-14), masked §10.1,
    filter MOD-12 (q + status dokumen), envelope berisi versi + checklist."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a)
    _seed_roster(auth_client, tenant_a, dep)
    _requirement(tenant_a, kind="ktp")
    _approve_doc(tenant_a, _pilgrim_by_name(tenant_a, "Sari Wijaya"), "ktp")

    response = _manifest(auth_client, dep.pk)
    assert response.status_code == 200, response.content
    payload = response.json()
    names = {row["name"] for row in payload["rows"]}
    assert names == {"Sari Wijaya", "Asep Nugraha"}  # terminal-excluded (UAT-14)
    assert payload["row_count"] == 2
    assert payload["departure"]["code"] == dep.code
    assert payload["versions"] == []
    assert {r["kind"] for r in payload["requirements"]} == {"ktp"}

    sari = next(r for r in payload["rows"] if r["name"] == "Sari Wijaya")
    asep = next(r for r in payload["rows"] if r["name"] == "Asep Nugraha")
    assert sari["docs_complete"] is True and sari["docs_missing"] == []
    assert asep["docs_complete"] is False and asep["docs_missing"] == ["ktp"]
    assert "identity_number" not in sari and "passport_number" not in sari  # masked only

    incomplete = _manifest(auth_client, dep.pk, "?document=incomplete").json()["rows"]
    assert [r["name"] for r in incomplete] == ["Asep Nugraha"]
    complete = _manifest(auth_client, dep.pk, "?document=complete").json()["rows"]
    assert [r["name"] for r in complete] == ["Sari Wijaya"]
    by_query = _manifest(auth_client, dep.pk, "?q=asep").json()["rows"]
    assert [r["name"] for r in by_query] == ["Asep Nugraha"]

    bad_filter = _manifest(auth_client, dep.pk, "?document=maybe")
    assert bad_filter.status_code == 400
    assert "document" in bad_filter.json()["field_errors"]

    # helper checklist terlihat di UI-12 (gerbang READY)
    gaps = _manifest(auth_client, dep.pk, "?checklist_gaps=1").json()["checklist_gaps"]
    assert gaps and "Asep Nugraha" in gaps[0]


@pytest.mark.django_db
def test_manifest_get_rbac_and_idor(auth_client, tenant_a, tenant_b):
    """§8.3 manifest = Ops/Admin/Owner; Sales/Finance 403; lintas tenant 404."""
    _seed_env(tenant_a)
    dep_a = _seed_departure(tenant_a)
    assert _manifest(auth_client, dep_a.pk).status_code == 200  # Owner lolos

    ops = Client()
    _make_member(ops, "ops-m@example.com", tenant_a, "Operations",
                 DEFAULT_ROLE_PERMISSIONS["Operations"])
    assert _manifest(ops, dep_a.pk).status_code == 200

    for role in ("Sales", "Finance"):
        client = Client()
        _make_member(client, f"{role.lower()}@example.com", tenant_a, role,
                     DEFAULT_ROLE_PERMISSIONS[role])
        assert _manifest(client, dep_a.pk).status_code == 403

    # IDOR: keberangkatan tenant lain tidak dikenal di konteks tenant_a (404)
    dep_b = _seed_departure(tenant_b)
    assert _manifest(auth_client, dep_b.pk).status_code == 404


@pytest.mark.django_db
def test_manifest_publish_versions_checksum_and_media(auth_client, tenant_a, media_root):
    """§7.6 snapshot publish: versi nomor urut unik, file JSON di storage,
    checksum sha256 isi, audit `manifest.published`; Sales tanpa publish."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a)
    _seed_roster(auth_client, tenant_a, dep)

    csrf = _csrf(auth_client)
    first = auth_client.post(
        f"/api/v1/departures/{dep.pk}/manifest/publish",
        {},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert first.status_code == 201, first.content
    v1 = first.json()["version"]
    assert v1["version_no"] == 1 and len(v1["checksum"]) == 64

    second = auth_client.post(
        f"/api/v1/departures/{dep.pk}/manifest/publish",
        {},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert second.status_code == 201 and second.json()["version"]["version_no"] == 2

    # file snapshot benar-benar ada + checksum cocok + isi = roster aktif saja
    with _as_tenant(tenant_a):
        version = ManifestVersion.objects.get(departure=dep, version_no=1)
    snapshot = media_root / version.snapshot_object_key
    assert snapshot.exists(), version.snapshot_object_key
    raw = snapshot.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == version.checksum
    data = json.loads(raw.decode())
    assert data["row_count"] == 2
    assert {r["name"] for r in data["rows"]} == {"Sari Wijaya", "Asep Nugraha"}
    assert data["version_no"] == 1 and data["departure"]["code"] == dep.code

    audit = AuditEvent.objects.filter(action="manifest.published").first()
    assert audit is not None and audit.changes_json["version_no"] == 2

    # versi nomor urut unik per departure (§5.2) — savepoint agar tes lanjut
    with _as_tenant(tenant_a):
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                ManifestVersion.objects.create(
                    tenant=tenant_a,
                    environment=Environment.DEMO,
                    departure=dep,
                    version_no=1,
                    snapshot_object_key="dup.json",
                    checksum="0" * 64,
                )

    sales = Client()
    _make_member(sales, "sales-m@example.com", tenant_a, "Sales",
                 DEFAULT_ROLE_PERMISSIONS["Sales"])
    denied = sales.post(
        f"/api/v1/departures/{dep.pk}/manifest/publish",
        {},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=_csrf(sales),
    )
    assert denied.status_code == 403


@pytest.mark.django_db
def test_manifest_publish_readonly_env(auth_client, tenant_a):
    """§2.2: environment read-only menolak publish (403), baca tetap jalan."""
    _seed_env(tenant_a, state=EnvironmentState.READ_ONLY)
    dep = _seed_departure(tenant_a)

    denied = auth_client.post(
        f"/api/v1/departures/{dep.pk}/manifest/publish",
        {},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=_csrf(auth_client),
    )
    assert denied.status_code == 403
    assert _manifest(auth_client, dep.pk).status_code == 200


# ------------------------------------------------------- ekspor CSV --


@pytest.mark.django_db
def test_export_csv_masked_uat14(auth_client, tenant_a):
    """Exit gate S10: CSV dasar — BOM UTF-8, prefiks DEMO- (§7.2), hanya
    peserta keberangkatan itu, PII tetap masked (§10.1), audit tercatat."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a)
    _seed_roster(auth_client, tenant_a, dep)
    pilgrim = _pilgrim_by_name(tenant_a, "Sari Wijaya")
    with _as_tenant(tenant_a):
        pilgrim.identity_encrypted = encrypt_pii("3201234567890001")
        pilgrim.passport_encrypted = encrypt_pii("C111222")
        pilgrim.identity_masked = "3201********0001"
        pilgrim.passport_masked = "C111***"
        pilgrim.save(
            update_fields=[
                "identity_encrypted",
                "passport_encrypted",
                "identity_masked",
                "passport_masked",
            ]
        )

    response = _csv(auth_client, dep.pk)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert "DEMO-manifest-" in response["Content-Disposition"]  # §7.2
    text = response.content.decode("utf-8")
    assert text.startswith("\ufeff")  # BOM Excel
    assert "Sari Wijaya" in text and "Asep Nugraha" in text
    assert "Budi Batal" not in text and "Tuti Expired" not in text  # UAT-14
    assert "3201234567890001" not in text and "C111222" not in text  # masked

    audit = AuditEvent.objects.filter(action="manifest.exported").first()
    assert audit is not None
    assert audit.changes_json["pii"] is False and audit.changes_json["rows"] == 2
    assert audit.changes_json["format"] == "csv"


@pytest.mark.django_db
def test_export_csv_pii_without_permission_denied_and_audited(auth_client, tenant_a):
    """OPS-03: ekspor PII tanpa izin → 403 DAN diaudit `manifest.export_denied`;
    ekspor non-PII tetap boleh bagi role ber-grant `manifest.export`."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a)
    _create_booking(auth_client, dep, [_seed_pilgrim(tenant_a, "Nurul")])  # Owner membuat

    ops_client = Client()
    _make_member(
        ops_client,
        "ops-export@example.com",
        tenant_a,
        "Operations",
        DEFAULT_ROLE_PERMISSIONS["Operations"],
    )

    masked = _csv(ops_client, dep.pk)  # manifest.export ✓
    assert masked.status_code == 200 and b"Nurul" in masked.content

    denied = _csv(ops_client, dep.pk, "?pii=1")
    assert denied.status_code == 403
    denial = AuditEvent.objects.filter(action="manifest.export_denied").first()
    assert denial is not None
    assert denial.changes_json["pii"] is True
    assert denial.object_id == str(dep.pk)


@pytest.mark.django_db
def test_export_csv_pii_with_owner_permission(auth_client, tenant_a):
    """Owner (matriks §3 = Y) mendapat nilai mentah NIK/paspor +
    kebutuhan khusus; flag PII terekam di audit `manifest.exported`."""
    _seed_env(tenant_a)
    dep = _seed_departure(tenant_a)
    p = _seed_pilgrim(tenant_a, "Zahra", special_needs="Kursi roda", address="Jl. Mawar 1")
    with _as_tenant(tenant_a):
        p.identity_encrypted = encrypt_pii("3205556667770002")
        p.passport_encrypted = encrypt_pii("X998877")
        p.save(update_fields=["identity_encrypted", "passport_encrypted"])
    _create_booking(auth_client, dep, [p])

    response = _csv(auth_client, dep.pk, "?pii=1")
    assert response.status_code == 200
    text = response.content.decode("utf-8")
    assert "3205556667770002" in text
    assert "X998877" in text
    assert "Kursi roda" in text  # kolom PII khusus

    audit = AuditEvent.objects.filter(action="manifest.exported").first()
    assert audit is not None and audit.changes_json["pii"] is True


# --------------------------------------------------------------- RLS --


@pytest.mark.django_db
@pytest.mark.parametrize("table", ["manifest_documentrequirement", "manifest_manifestversion"])
def test_manifest_tables_have_enforced_rls_policy(db, table):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s",
            [table],
        )
        assert cursor.fetchone() == (True, True), f"{table} harus ENABLE+FORCE RLS (ADR-0003 §3)"
        cursor.execute("SELECT qual, with_check FROM pg_policies WHERE tablename = %s", [table])
        policy = cursor.fetchone()
        assert policy is not None
        for clause in policy:
            assert "current_setting('app.tenant_id'" in clause
            assert "NULLIF" in clause
