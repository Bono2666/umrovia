"""Environment helpers terpusat untuk settings."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # root repo


def env(key: str, default: str | None = None, *, required: bool = False) -> str | None:
    """Baca environment variable; gagal cepat bila wajib dan tidak ada (Spec §19.6)."""
    value = os.environ.get(key, default)
    if required and value in (None, ""):
        raise RuntimeError(f"Environment variable {key} wajib diisi tetapi belum di-set (lihat .env.example)")
    return value


def env_bool(key: str, default: str = "False") -> bool:
    return str(env(key, default)).lower() in ("1", "true", "yes", "on")


def env_list(key: str, default: str = "") -> list[str]:
    raw = env(key, default) or ""
    return [item.strip() for item in raw.split(",") if item.strip()]
