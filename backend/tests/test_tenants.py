"""S01/T05+T06 — tenancy: constraint, context tenant, scoped query (deny tanpa context)."""
import pytest
from django.core.exceptions import ValidationError

from modules.tenants.context import get_current_tenant, set_current_tenant
from modules.tenants.managers import TenantContextMissingError, TenantScopedModel
from modules.tenants.models import MembershipStatus, Tenant, TenantMembership


@pytest.mark.django_db
def test_tenant_slug_unique(db, tenant_a):
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        Tenant.objects.create(slug="travel-a", legal_name="PT Duplikat", display_name="Duplikat")


@pytest.mark.django_db
def test_reserved_slug_rejected(db):
    tenant = Tenant(slug="admin", legal_name="PT Nakal", display_name="Nakal")
    with pytest.raises(ValidationError):
        tenant.full_clean()


@pytest.mark.django_db
def test_membership_unique_per_tenant_user(db, owner_a, user, tenant_b):
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError), transaction.atomic():
        TenantMembership.objects.without_tenant_guard().create(
            tenant=owner_a.tenant, user=user, status=MembershipStatus.ACTIVE
        )
    # user yang sama boleh join tenant lain
    other = TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant_b, user=user, status=MembershipStatus.INVITED
    )
    assert other.pk


@pytest.mark.django_db
def test_context_set_and_clear(db, tenant_a):
    assert get_current_tenant() is None
    set_current_tenant(tenant_a)
    assert get_current_tenant().slug == "travel-a"
    set_current_tenant(None)


@pytest.mark.django_db
def test_scoped_model_denied_without_context(db, tenant_a, owner_a):
    """Fail-closed: query tenant-scoped tanpa context harus DITOLAK, bukan kosong."""

    class Probe(TenantScopedModel):
        class Meta:
            app_label = "tenants"

    assert get_current_tenant() is None
    with pytest.raises(TenantContextMissingError):
        Probe.objects.all()


@pytest.mark.django_db
def test_scoped_queryset_filters_by_current_tenant(db, tenant_a, tenant_b, owner_a):
    set_current_tenant(tenant_a)
    memberships = TenantMembership.objects.for_current_tenant()
    assert {m.tenant.slug for m in memberships} == {"travel-a"}
    set_current_tenant(None)


@pytest.mark.django_db
def test_middleware_sets_tenant_from_membership(client, user, owner_a):
    client.force_login(user)
    response = client.get("/api/v1/health/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_two_tenants_isolated_at_query_level(db, tenant_a, tenant_b, owner_a):
    """Dua tenant: membership tenant A tidak terlihat dari context tenant B."""
    from modules.identity.models import User

    user_b = User.objects.create_user(email="b@example.com", password="x-pass-123")
    TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant_b, user=user_b, status=MembershipStatus.ACTIVE
    )

    set_current_tenant(tenant_a)
    emails_a = {m.user.email for m in TenantMembership.objects.for_current_tenant()}
    set_current_tenant(tenant_b)
    emails_b = {m.user.email for m in TenantMembership.objects.for_current_tenant()}

    assert "owner@example.com" in emails_a and "b@example.com" not in emails_a
    assert emails_b == {"b@example.com"}
    set_current_tenant(None)
