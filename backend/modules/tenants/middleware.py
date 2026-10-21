"""TenantContextMiddleware — S01 skeleton (resolver lengkap: F02/S03).

S01: set context tenant dari membership ACTIVE pertama user (server-side lookup —
tidak mempercayai input client). Workspace switch eksplisit & host/slug resolver
menyusul di S02–S03 bersama RLS.
"""
import logging

from modules.tenants.context import set_current_tenant
from modules.tenants.models import MembershipStatus, TenantMembership

logger = logging.getLogger(__name__)


class TenantContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = set_current_tenant(None)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            # Resolusi membership = jalur bootstrap tanpa context → bypass guard (wajib via query server-side).
            membership = (
                TenantMembership.objects.without_tenant_guard()
                .filter(user=user, status=MembershipStatus.ACTIVE)
                .select_related("tenant")
                .order_by("created_at")
                .first()
            )
            if membership is not None:
                token = set_current_tenant(membership.tenant)
                request.tenant = membership.tenant
                request.membership = membership
        try:
            return self.get_response(request)
        finally:
            set_current_tenant(None)
            del token
