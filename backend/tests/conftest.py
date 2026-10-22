import pytest
from django.core.cache import cache
from django.utils import timezone

from modules.identity.models import User
from modules.tenants.models import Role, Tenant, TenantMembership


@pytest.fixture(autouse=True)
def _reset_throttle_cache():
    """Bersihkan riwayat throttle antar-test (LocMemCache persisten dalam satu proses)."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _no_throttle():
    """Rate limit dinonaktifkan untuk semua test (kecuali test throttle yang patch balik).

    DRF men-snapshot `DEFAULT_THROTTLE_RATES` ke class attribute saat import,
    jadi override harus menyentuh `SimpleRateThrottle.THROTTLE_RATES` langsung.
    """
    from rest_framework.throttling import SimpleRateThrottle

    original = SimpleRateThrottle.THROTTLE_RATES
    SimpleRateThrottle.THROTTLE_RATES = {scope: "10000/hour" for scope in original}
    yield
    SimpleRateThrottle.THROTTLE_RATES = original


@pytest.fixture
def user(db) -> User:
    u = User.objects.create_user(email="Owner@Example.com", password="rahasia123", full_name="Owner Demo")
    u.email_verified_at = timezone.now()
    u.status = "ACTIVE"
    u.save()
    return u


@pytest.fixture
def verified_user(db) -> User:
    from django.utils import timezone

    from modules.identity.models import UserStatus

    u = User.objects.create_user(
        email="verified@example.com", password="rahasia123", full_name="Verified User"
    )
    u.email_verified_at = timezone.now()
    u.status = UserStatus.ACTIVE
    u.save()
    return u


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


@pytest.fixture
def auth_client(client, user, owner_a):
    """Client yang sudah login sebagai owner_a."""
    client.force_login(user)
    return client


def token_from_mail(mail) -> str:
    """Ambil token mentah dari link terakhir di outbox email."""
    import re

    body = mail[-1].body
    match = re.search(r"token=([A-Za-z0-9_\-]+)", body)
    assert match, f"token tidak ditemukan di email: {body[:200]}"
    return match.group(1)
