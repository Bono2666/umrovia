"""Job `notification_sender` (Spec §11.2): kirim antrean email dengan backoff dan DLQ."""
import time

from django.core.management.base import BaseCommand

from modules.notifications.services import process_queue


class Command(BaseCommand):
    help = "Kirim notifikasi email yang jatuh tempo; gagal → dicoba ulang dengan backoff, habis → DEAD."

    def add_arguments(self, parser):
        parser.add_argument("--batch", type=int, default=None)
        parser.add_argument("--loop", action="store_true", help="Terus berjalan (gunakan run_worker untuk semua job).")
        parser.add_argument("--interval", type=float, default=5.0)

    def handle(self, *args, **options):
        while True:
            result = process_queue(options["batch"])
            if any(result.values()) or not options["loop"]:
                self.stdout.write(" ".join(f"{key}={value}" for key, value in result.items()))
            if not options["loop"]:
                return
            time.sleep(options["interval"])
