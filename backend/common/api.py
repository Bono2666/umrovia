"""API helpers — error style RFC7807 (Problem Details) sesuai Spec §8."""
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, Throttled, ValidationError
from rest_framework.views import exception_handler as drf_exception_handler

from common.request_context import get_request_id


class ProblemDetailAPIException(APIException):
    """Base exception yang dipetakan ke format {type,title,status,code,detail,request_id}."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "bad_request"
    default_title = "Bad Request"

    def __init__(self, detail=None, code=None):
        super().__init__(detail=detail, code=code)


def _problem_payload(exc, request) -> dict:
    code = getattr(exc, "code", None) or getattr(exc, "default_code", None) or "error"
    status_code = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
    detail = getattr(exc, "detail", str(exc))
    field_errors = None
    if isinstance(detail, dict):
        field_errors = {k: (v if isinstance(v, list) else [v]) for k, v in detail.items()}
        detail = "Validasi gagal pada field tertentu."
    elif isinstance(detail, list):
        detail = " ".join(str(item) for item in detail)
    return {
        "type": f"https://umrovia.com/problems/{code}",
        "title": getattr(exc, "default_title", "Error"),
        "status": status_code,
        "code": code,
        "detail": str(detail),
        "request_id": get_request_id(),
        "timestamp": timezone.now().isoformat(),
        "field_errors": field_errors,
    }


def exception_handler(exc, context):
    """Exception handler DRF: response RFC7807-style + request_id."""
    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    if isinstance(exc, Throttled):
        exc.code = "rate_limited"  # peta ke semangat §8.9 RATE_LIMITED
    elif isinstance(exc, ValidationError) and getattr(exc, "code", None) is None:
        exc.code = "bad_request"  # kode stabil untuk kegagalan validasi input
    request = context.get("request")
    payload = _problem_payload(exc, request)
    response.data = payload
    return response
