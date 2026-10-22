"""Exception domain tenant — kode error mengikuti Spec §8.9 (huruf besar)."""
from rest_framework import status

from common.api import ProblemDetailAPIException


class TenantContextRequired(ProblemDetailAPIException):
    """Endpoint tenant-scoped dipanggil tanpa context tenant valid (fail-closed)."""

    status_code = status.HTTP_403_FORBIDDEN
    default_code = "TENANT_CONTEXT_REQUIRED"
    default_title = "Tenant context required"
    default_detail = "Context tenant tidak tersedia untuk permintaan ini."


class TenantAccessDenied(ProblemDetailAPIException):
    """User tidak berhak mengakses workspace/objek tenant tertentu."""

    status_code = status.HTTP_403_FORBIDDEN
    default_code = "TENANT_ACCESS_DENIED"
    default_title = "Tenant access denied"
    default_detail = "Anda tidak memiliki akses ke workspace tersebut."
