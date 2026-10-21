"""Middleware bersama Umrovia."""
import logging
import uuid

from common.request_context import set_request_id

logger = logging.getLogger(__name__)


class RequestIDMiddleware:
    """T10: setiap request punya request_id (terima dari gateway atau buat baru),
    dikembalikan di header X-Request-ID dan dilampirkan ke logging context."""

    HEADER = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.META.get("HTTP_X_REQUEST_ID", "")
        request_id = incoming if 0 < len(incoming) <= 64 else uuid.uuid4().hex
        request.request_id = request_id
        token = set_request_id(request_id)
        try:
            response = self.get_response(request)
        finally:
            set_request_id(None)
            del token
        response[self.HEADER] = request_id
        return response
