"""Layanan domain jamaah (S07).

Implementasi resolusi environment + guard write pindah ke rumah bersama
`modules.tenants.environment` (S08) — di-re-export agar import lama tetap sah.
"""
from modules.tenants.environment import (  # noqa: F401
    EnvironmentReadOnlyError,
    assert_environment_writable,
    resolve_active_environment,
)

__all__ = [
    "EnvironmentReadOnlyError",
    "assert_environment_writable",
    "resolve_active_environment",
]
