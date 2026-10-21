"""Tenant context per-request (Spec §2.2).

Identifier tenant berasal dari membership tervalidasi (host/slug resolver di F02) —
bukan dari input client. Context memakai ContextVar agar aman untuk thread/async.
"""
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from modules.tenants.models import Tenant

_tenant: ContextVar["Tenant | None"] = ContextVar("umrovia_tenant", default=None)


def set_current_tenant(tenant: "Tenant | None"):
    return _tenant.set(tenant)


def get_current_tenant() -> "Tenant | None":
    return _tenant.get()


def clear_current_tenant(token) -> None:
    _tenant.reset(token)
