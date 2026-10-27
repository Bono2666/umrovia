"""Worker latar belakang (Spec §11.2): antrean notifikasi + job terjadwal sederhana.

Satu proses, interval tetap; setiap job idempoten sehingga aman bila worker
di-restart atau dijalankan lebih dari satu (klaim antrean memakai SKIP LOCKED).
"""
import logging
import signal
import time

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from modules.notifications.services import process_queue

logger = logging.getLogger(__name__)

SCHEDULE = [  # (perintah, interval detik)
    ("expire_trials", 3600),
    ("send_trial_reminders", 3600),
    ("retry_pending_charges", 900),
    ("verify_integrity", 86400),  # S19: backup_validation / reconciliation_daily (read-only)
]


class Command(BaseCommand):
    help = "Jalankan worker: kirim notifikasi tiap beberapa detik dan job terjadwal (trial, pending charge)."

    def handle(self, *args, **options):
        stopping = []
        signal.signal(signal.SIGTERM, lambda *_: stopping.append(True))
        # -inf: setiap job berjalan sekali saat worker start. (0.0 keliru: monotonic() dihitung sejak
        # mesin menyala, sehingga job ber-interval > uptime tidak pernah berjalan saat start.)
        last_run = {name: float("-inf") for name, _ in SCHEDULE}
        self.stdout.write("worker: berjalan")
        while not stopping:
            close_old_connections()
            try:  # heartbeat untuk /health (S19 monitoring); cache bersama = Redis di Docker/produksi
                cache.set("worker:heartbeat", time.time(), 600)
            except Exception as exc:  # noqa: BLE001
                logger.error("worker heartbeat failed; error=%s", type(exc).__name__)
            for name, interval in SCHEDULE:
                if time.monotonic() - last_run[name] >= interval:
                    last_run[name] = time.monotonic()
                    try:
                        call_command(name, stdout=self.stdout)
                    except Exception as exc:  # noqa: BLE001 — job lain tetap berjalan
                        logger.error("worker job failed; job=%s error=%s", name, type(exc).__name__)
            try:
                result = process_queue()
                if any(result.values()):
                    self.stdout.write("notifications: " + " ".join(f"{key}={value}" for key, value in result.items()))
            except Exception as exc:  # noqa: BLE001
                logger.error("worker notifications failed; error=%s", type(exc).__name__)
            time.sleep(settings.WORKER_INTERVAL_SECONDS)
        self.stdout.write("worker: berhenti")
