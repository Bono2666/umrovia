"""Regresi hasil audit penyelesaian S07–S10."""
from contextlib import contextmanager
from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection
from django.utils import timezone

from modules.booking.models import Booking, BookingParticipant
from modules.catalog.models import TravelPackage
from modules.departures.models import Departure
from modules.identity.models import User
from modules.manifest.models import DocumentRequirement
from modules.manifest.services import effective_requirements, publish_manifest
from modules.pilgrims.models import Pilgrim, PilgrimDocument
from modules.tenants.context import clear_current_tenant, set_current_tenant
from modules.tenants.models import Role, TenantEnvironment, TenantMembership


@contextmanager
def tenant_context(tenant):
    token = set_current_tenant(tenant)
    try:
        yield
    finally:
        clear_current_tenant(token)


def operational_records(tenant, environment="demo"):
    """Satu peserta booking aktif pada keberangkatan, tanpa dokumen."""
    with tenant_context(tenant):
        package = TravelPackage.objects.create(
            tenant=tenant, environment=environment, code=f"PKT-{uuid4().hex[:8]}", name="Audit"
        )
        departure = Departure.objects.create(
            tenant=tenant, environment=environment, package=package,
            code=f"DPR-{uuid4().hex[:8]}", start_at=timezone.now() + timedelta(days=30),
            city_of_origin="Jakarta", seat_capacity=10, seats_taken=1, status="OPEN",
        )
        pilgrim = Pilgrim.objects.create(
            tenant=tenant, environment=environment, code=f"JM-{uuid4().hex[:8]}", name="Jamaah Audit"
        )
        booking = Booking.objects.create(
            tenant=tenant, environment=environment, departure=departure,
            code=f"BK-{uuid4().hex[:8]}", status="RESERVED",
        )
        BookingParticipant.objects.create(
            tenant=tenant, environment=environment, booking=booking, pilgrim=pilgrim,
            participant_status="REGISTERED",
        )
    return departure, pilgrim


@pytest.mark.django_db
@pytest.mark.parametrize("environments", [("demo", "production"), ("production", "demo")])
def test_manifest_checklists_stay_in_their_environment(auth_client, tenant_a, environments):
    records = {}
    for environment in environments:
        TenantEnvironment.objects.create(tenant=tenant_a, environment=environment, state="ACTIVE")
        records[environment] = operational_records(tenant_a, environment)
        with tenant_context(tenant_a):
            DocumentRequirement.objects.create(
                tenant=tenant_a, environment=environment, kind="passport", mandatory=environment == "demo"
            )
            DocumentRequirement.objects.create(
                tenant=tenant_a, environment=environment, kind="ktp" if environment == "demo" else "photo"
            )
    for environment, (departure, _) in records.items():
        expected = {"passport", "ktp" if environment == "demo" else "photo"}
        with tenant_context(tenant_a):
            requirements = effective_requirements(departure.package)
            assert {r.kind for r in requirements} == expected
            assert {r.environment for r in requirements} == {environment}
        response = auth_client.get(f"/api/v1/departures/{departure.pk}/manifest?checklist_gaps=1")
        assert response.status_code == 200
        payload = response.json()
        assert {r["environment"] for r in payload["requirements"]} == {environment}
        required = {"passport", "ktp"} if environment == "demo" else {"photo"}
        assert set(payload["rows"][0]["docs_missing"]) == required
        assert len(payload["checklist_gaps"]) == len(required)


@pytest.mark.django_db
def test_readiness_requires_approval_of_latest_document(auth_client, tenant_a):
    TenantEnvironment.objects.create(tenant=tenant_a, environment="demo", state="ACTIVE")
    departure, pilgrim = operational_records(tenant_a)
    with tenant_context(tenant_a):
        DocumentRequirement.objects.create(tenant=tenant_a, environment="demo", kind="passport")
        for version, status in [(1, "APPROVED"), (2, "UPLOADED")]:
            doc = PilgrimDocument.objects.create(
                tenant=tenant_a, environment="demo", pilgrim=pilgrim, kind="passport",
                object_key=f"tenants/{tenant_a.pk}/environments/demo/pilgrims/{pilgrim.pk}/v{version}.pdf",
                version=version, status=status,
            )
    csrf = auth_client.get("/api/v1/auth/csrf").json()["csrfToken"]
    url = f"/api/v1/departures/{departure.pk}/transition"
    response = auth_client.post(url, {"target": "READY"}, content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 400
    assert "checklist" in response.json()["field_errors"]
    with tenant_context(tenant_a):
        doc.status = "APPROVED"
        doc.save(update_fields=["status"])
    response = auth_client.post(url, {"target": "READY"}, content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
    assert response.status_code == 200


@pytest.mark.django_db
def test_published_manifest_cannot_be_edited_or_deleted(tenant_a, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    departure, _ = operational_records(tenant_a)
    with tenant_context(tenant_a):
        version = publish_manifest(departure=departure)
        checksum = version.checksum
        version.checksum = "0" * 64
        with pytest.raises(ValidationError, match="append-only"):
            version.save()
        with pytest.raises(ValidationError, match="append-only"):
            version.delete()
        version.refresh_from_db()
        assert version.checksum == checksum
        following = publish_manifest(departure=departure)
        assert following.version_no == 2


@pytest.mark.django_db
@pytest.mark.parametrize("payload", [{}, {"reason": "Tanpa status"}])
def test_document_review_without_status_returns_validation_error(auth_client, tenant_a, payload):
    TenantEnvironment.objects.create(tenant=tenant_a, environment="demo", state="ACTIVE")
    _, pilgrim = operational_records(tenant_a)
    with tenant_context(tenant_a):
        doc = PilgrimDocument.objects.create(
            tenant=tenant_a, environment="demo", pilgrim=pilgrim, kind="passport", object_key="audit.pdf"
        )
    csrf = auth_client.get("/api/v1/auth/csrf").json()["csrfToken"]
    response = auth_client.patch(
        f"/api/v1/pilgrims/{pilgrim.pk}/documents/{doc.pk}", payload,
        content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 400
    assert "status" in response.json()["field_errors"]
    doc.refresh_from_db()
    assert doc.status == "UPLOADED" and doc.reviewed_by_id is None


@pytest.mark.django_db
def test_departure_pic_is_an_active_staff_member_of_this_tenant(auth_client, user, tenant_a, tenant_b):
    TenantEnvironment.objects.create(tenant=tenant_a, environment="demo", state="ACTIVE")
    departure, _ = operational_records(tenant_a)
    foreign = User.objects.create_user(email="foreign@example.test", status="ACTIVE")
    invited = User.objects.create_user(email="invited@example.test", status="ACTIVE")
    suspended = User.objects.create_user(email="suspended@example.test", status="SUSPENDED")
    for person, tenant, status in [(foreign, tenant_b, "ACTIVE"), (invited, tenant_a, "INVITED"), (suspended, tenant_a, "ACTIVE")]:
        TenantMembership.objects.without_tenant_guard().create(tenant=tenant, user=person, status=status)
    csrf = auth_client.get("/api/v1/auth/csrf").json()["csrfToken"]
    for person in [foreign, invited, suspended]:
        response = auth_client.patch(
            f"/api/v1/departures/{departure.pk}", {"lead_staff": str(person.pk)},
            content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
        )
        assert response.status_code == 400
        assert "lead_staff" in response.json()["field_errors"]
    response = auth_client.patch(
        f"/api/v1/departures/{departure.pk}", {"lead_staff": str(user.pk)},
        content_type="application/json", HTTP_X_CSRFTOKEN=csrf,
    )
    assert response.status_code == 200 and response.json()["lead_staff"] == str(user.pk)
    response = auth_client.get("/api/v1/departures/staff")
    assert response.status_code == 200
    assert response.json()["results"] == [{"id": str(user.pk), "name": user.full_name}]


@pytest.mark.django_db
def test_staff_picker_uses_departure_permissions(client, user, tenant_a):
    role = Role.objects.create(tenant=tenant_a, name="Ops audit", permissions_json=["departures.write"])
    TenantMembership.objects.without_tenant_guard().create(tenant=tenant_a, user=user, role=role, status="ACTIVE")
    client.force_login(user)
    assert client.get("/api/v1/departures/staff").status_code == 200
    role.permissions_json = ["departures.read"]
    role.save(update_fields=["permissions_json"])
    assert client.get("/api/v1/departures/staff").status_code == 403
    client.logout()
    assert client.get("/api/v1/departures/staff").status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("stage", [0, 1, 2])
def test_legacy_default_roles_upgrade_without_changing_custom_roles(tenant_a, tenant_b, stage):
    migration = import_module("modules.tenants.migrations.0005_operational_role_defaults")
    for name, baseline in migration.LEGACY_ROLES.items():
        grants = list(baseline)
        for additions in migration.SPRINT_ADDITIONS[:stage]:
            grants.extend(additions.get(name, []))
        Role.objects.create(tenant=tenant_a, name=name, permissions_json=grants)
    custom = Role.objects.create(tenant=tenant_b, name="Admin", permissions_json=["pilgrims.read"])
    owner = Role.objects.create(tenant=tenant_b, name="Owner", permissions_json=["*"], is_system=True)
    editor = SimpleNamespace(connection=connection)
    migration.upgrade_operational_roles(apps, editor)
    migration.upgrade_operational_roles(apps, editor)  # idempoten
    for role in Role.objects.filter(tenant=tenant_a):
        expected = list(migration.LEGACY_ROLES[role.name])
        for additions in migration.SPRINT_ADDITIONS:
            expected.extend(additions.get(role.name, []))
        assert set(role.permissions_json) == set(expected)
        assert "manifest.export_pii" not in role.permissions_json
    custom.refresh_from_db()
    owner.refresh_from_db()
    assert custom.permissions_json == ["pilgrims.read"]
    assert owner.permissions_json == ["*"]
