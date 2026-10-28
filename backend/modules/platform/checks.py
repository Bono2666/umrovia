"""System check: tanpa penerima, pesan formulir kontak tersimpan tetapi tidak ada yang diberi tahu."""
from django.conf import settings
from django.core import checks


@checks.register()
def contact_recipient_configured(app_configs, **kwargs):
    if settings.DEBUG or settings.CONTACT_RECIPIENT_EMAIL:
        return []
    return [checks.Warning(
        "CONTACT_RECIPIENT_EMAIL kosong: pesan formulir kontak tersimpan tanpa notifikasi email.",
        hint="Isi CONTACT_RECIPIENT_EMAIL di .env.production, lalu jalankan ulang api.",
        id="platform.W001",
    )]
