"""Job `trial_reminders` (Spec §11.2, TR07): H-7/H-3/H-1, satu pesan per penerima per hari pengingat."""
from django.core.management.base import BaseCommand

from modules.notifications.services import send_trial_reminders


class Command(BaseCommand):
    help = "Antrekan pengingat akhir trial untuk owner (idempoten)."

    def handle(self, *args, **options):
        self.stdout.write(f"trial_reminders: {send_trial_reminders()} pesan diantrekan")
