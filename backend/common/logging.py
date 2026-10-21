"""Logging terstruktur + request ID (T10 — tanpa PII/secrets di log, Spec §13)."""
import json
import logging
import time

from common.request_context import get_request_id

_RESERVED_ATTRS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName", "levelname",
    "levelno", "lineno", "module", "msecs", "message", "msg", "name", "pathname", "process",
    "processName", "relativeCreated", "stack_info", "taskName", "thread", "threadName",
}


class RequestIDFilter(logging.Filter):
    """Selipkan request_id ke setiap record dari konteks thread-local."""

    def filter(self, record):
        record.request_id = get_request_id()
        return True


class StructuredFormatter(logging.Formatter):
    """Format JSON satu baris; hanya field aman (tanpa payload/bearer/PII)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and key != "request_id" and not key.startswith("_"):
                payload[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = record.exc_info[0].__name__
        return json.dumps(payload, default=str)
