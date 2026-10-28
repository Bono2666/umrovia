"""Tenant resolver — identitas tenant dari domain/slug tervalidasi (Spec §2.2).

Urutan resolusi (lihat TenantContextMiddleware):
1. Subdomain host: `<slug>.umrovia.com` / `<slug>.localhost` (dev) — identitas eksplisit.
2. Sesi workspace hasil `POST /workspaces/switch` (divalidasi server-side saat switch).
3. Fallback dev-local: membership ACTIVE pertama user (tanpa subdomain/switch).

Client-supplied `?tenant_id`/header TIDAK PERNAH dipercai (Spec §2.2).
"""
import re

from django.conf import settings

from modules.tenants.constants import RESERVED_SLUGS

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def slug_from_host(host: str | None) -> str | None:
    """Ambil slug tenant dari subdomain host. Bukan subdomain → None.

    Host layanan sendiri (`api.`, `app.`, `admin.`, … = RESERVED_SLUGS) bukan identitas
    tenant: tanpa pengecualian ini setiap request ke `api.umrovia.com` dianggap
    workspace bernama "api" sehingga context tenant selalu kosong (403).
    """
    if not host:
        return None
    hostname = host.split(":")[0].lower()
    for base in settings.TENANT_DOMAIN_BASES:
        suffix = "." + base
        if hostname.endswith(suffix):
            candidate = hostname[: -len(suffix)]
            if candidate and SLUG_RE.match(candidate) and candidate not in RESERVED_SLUGS:
                return candidate
    return None
