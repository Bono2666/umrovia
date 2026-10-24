"""Email notifications for consented public website enquiries."""

import logging

from django.conf import settings
from django.core.mail import EmailMessage

from modules.platform.models import ContactMessage

logger = logging.getLogger(__name__)


def send_contact_notification(message: ContactMessage) -> None:
    """Notify the configured inbox; retain the saved enquiry if email fails."""
    email = EmailMessage(
        subject=f"[Umrovia] {message.get_topic_display()} — {message.pk}",
        body=(
            f"Pesan baru dari formulir kontak Umrovia.\n\n"
            f"Referensi: {message.pk}\n"
            f"Topik: {message.get_topic_display()}\n"
            f"Nama: {message.name}\n"
            f"Travel / perusahaan: {message.company or '-'}\n"
            f"Email: {message.email}\n"
            f"Telepon: {message.phone or '-'}\n\n"
            f"Pesan:\n{message.message}\n\n"
            "Pengunjung menyetujui pemrosesan data untuk menanggapi pesan ini.\n"
            "Gunakan Reply untuk membalas langsung kepada pengunjung.\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[settings.CONTACT_RECIPIENT_EMAIL],
        reply_to=[message.email],
    )
    try:
        if email.send() != 1:
            logger.error("contact: email notification not sent; reference=%s", message.pk)
    except Exception as exc:
        # Do not expose backend errors or visitor details in the public API/logs.
        # The saved message remains available to staff through Django admin.
        logger.error("contact: email notification failed; reference=%s; error=%s", message.pk, type(exc).__name__)
