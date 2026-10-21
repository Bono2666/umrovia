"""Thread-local request context (request_id, tenant_id) — aman untuk ASGI/threads."""
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(value: str | None):
    return _request_id.set(value)


def get_request_id() -> str | None:
    return _request_id.get()
