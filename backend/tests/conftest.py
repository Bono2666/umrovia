import pytest

from modules.identity.models import User
from modules.tenants.models import Role, Tenant, TenantMembership


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(email="Owner@Example.com", password="rahasia123", full_name="Owner Demo")


@pytest.fixture
def tenant_a(db) -> Tenant:
    return Tenant.objects.create(slug="travel-a", legal_name="PT Travel A", display_name="Travel A")


@pytest.fixture
def tenant_b(db) -> Tenant:
    return Tenant.objects.create(slug="travel-b", legal_name="PT Travel B", display_name="Travel B")


@pytest.fixture
def owner_a(db, user, tenant_a) -> TenantMembership:
    role = Role.objects.create(tenant=tenant_a, name="Owner", permissions_json={"*": True})
    # provisioning tanpa context tenant → jalur bypass yang sah
    return TenantMembership.objects.without_tenant_guard().create(
        tenant=tenant_a, user=user, role=role, status="ACTIVE"
    )
