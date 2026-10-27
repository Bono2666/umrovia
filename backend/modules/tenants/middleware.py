"""TenantContextMiddleware — resolve tenant + SET LOCAL app.tenant_id (Spec §2.2).

Resolusi (server-side, tanpa input client yang dipercaya):
1. subdomain host (`<slug>.umrovia.com` / `<slug>.localhost`) →
2. sesi hasil `POST /workspaces/switch` →
3. fallback dev-local: membership ACTIVE pertama.

Setelah membership dikonfirmasi, seluruh request dibungkus `transaction.atomic()`
dengan `SET LOCAL app.tenant_id` pada koneksi request-bound — nilai otomatis
dihapus saat transaksi berakhir (commit/rollback), jadi tidak pernah bocor ke
request berikutnya pada koneksi pool (§2.2, ADR-0003). Tanpa context, kebijakan
RLS gagal-tertutup (fail-closed).
"""
import logging

from django.db import connection, transaction
from django.http import JsonResponse

from common.request_context import get_request_id
from modules.tenants.context import clear_current_tenant, set_current_tenant
from modules.tenants.models import BLOCKED_STATES, MembershipStatus, TenantMembership
from modules.tenants.resolver import slug_from_host

logger = logging.getLogger(__name__)

# S18: workspace ditangguhkan/diakhiri platform hanya boleh mengakses akun, pemilihan
# workspace dan tiket dukungan; seluruh API operasional tenant ditolak (fail-closed).
SUSPENDED_ALLOWED_PREFIXES = ("/api/v1/me", "/api/v1/auth/", "/api/v1/workspaces/", "/api/v1/support/", "/api/v1/health/", "/api/v1/platform/", "/api/v1/portal/", "/api/v1/contact")


def suspended_response(tenant):
    terminated = tenant.state == "TERMINATED"
    detail = ("Workspace travel ini telah diakhiri oleh platform." if terminated
              else "Workspace travel ini sedang ditangguhkan oleh platform. Hubungi dukungan Umrovia melalui menu Bantuan.")
    code = "tenant_terminated" if terminated else "tenant_suspended"
    return JsonResponse({"type": f"https://umrovia.com/problems/{code}", "title": "Workspace tidak aktif", "status": 403, "code": code,
                         "detail": detail, "request_id": get_request_id()}, status=403)


class TenantContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _resolve_membership(request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        # Bootstrap query tanpa context → wajib bypass guard (server-side lookup).
        memberships = TenantMembership.objects.without_tenant_guard().filter(
            user=user, status=MembershipStatus.ACTIVE
        ).select_related("tenant")

        slug = slug_from_host(request.get_host())
        if slug is None:
            slug = request.session.get("active_tenant_slug")
        if slug is not None:
            # Host/sesi menunjuk workspace tertentu → wajib membership valid di sana.
            # Gagal = context kosong (fail-closed), BUKAN fallback diam-diam ke
            # tenant lain — mencegah salah-baca data lintas tenant.
            return memberships.filter(tenant__slug=slug).first()
        # Dev/local tanpa subdomain: membership aktif pertama (deterministik).
        return memberships.order_by("created_at").first()

    def __call__(self, request):
        token = set_current_tenant(None)
        request.tenant = None
        request.membership = None
        try:
            membership = self._resolve_membership(request)
            if (membership is not None and membership.tenant.state in BLOCKED_STATES
                    and request.path.startswith("/api/v1/") and not request.path.startswith(SUSPENDED_ALLOWED_PREFIXES)):
                return suspended_response(membership.tenant)
            if membership is not None:
                request.tenant = membership.tenant
                request.membership = membership
                set_current_tenant(membership.tenant)

            with transaction.atomic():
                if membership is not None:
                    # SET LOCAL di dalam transaksi request (koneksi request-bound);
                    # otomatis di-rollback oleh mekanisme transaksi PostgreSQL.
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT set_config('app.tenant_id', %s, TRUE)",
                            [str(membership.tenant_id)],
                        )
                return self.get_response(request)
        finally:
            clear_current_tenant(token)
