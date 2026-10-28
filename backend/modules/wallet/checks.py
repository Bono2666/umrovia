"""System check: mode Midtrans harus cocok dengan jenis server key (sandbox `SB-…` vs produksi)."""
from django.conf import settings
from django.core import checks


@checks.register()
def midtrans_key_matches_mode(app_configs, **kwargs):
    key = settings.MIDTRANS_SERVER_KEY.strip()
    if not key:
        return []
    sandbox_key = key.startswith("SB-")
    if settings.MIDTRANS_IS_PRODUCTION and sandbox_key:
        # Warning, bukan Error: Error menggagalkan migrate saat start sehingga seluruh API mati.
        return [checks.Warning("MIDTRANS_IS_PRODUCTION=True tetapi MIDTRANS_SERVER_KEY adalah key sandbox (SB-…).",
                               hint="Pakai Server Key dari dashboard Midtrans Production.", id="wallet.W002")]
    if not settings.MIDTRANS_IS_PRODUCTION and not sandbox_key:
        return [checks.Warning("MIDTRANS_SERVER_KEY tampak key produksi, tetapi MIDTRANS_IS_PRODUCTION=False (sandbox).",
                               hint="Isi MIDTRANS_IS_PRODUCTION=True, atau pakai key sandbox SB-Mid-server-….", id="wallet.W001")]
    return []
