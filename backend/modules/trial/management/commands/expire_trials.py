"""Job `trial_expiry` (Spec §6.1/§11; cron per jam — orkestrasi S17).

Konversi trial yang `now_utc >= ends_at` → ACTIVE otomatis tanpa biaya (TR08),
dengan lock baris & re-check status agar aman terhadap race konversi dini.
"""
from django.core.management.base import BaseCommand

from modules.trial.services import expire_due_trials


class Command(BaseCommand):
    help = "Konversi trial yang jatuh tempo → ACTIVE tanpa charge (Spec §6.1, TR08)."

    def handle(self, *args, **options):
        processed = expire_due_trials()
        self.stdout.write(self.style.SUCCESS(f"expire_trials: {processed} trial dikonversi"))
