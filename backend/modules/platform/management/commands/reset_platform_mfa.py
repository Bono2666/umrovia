"""Reset MFA staf platform yang kehilangan perangkat (dijalankan operator infrastruktur, tercatat di audit)."""
from django.core.management.base import BaseCommand, CommandError

from modules.audit.services import log_event
from modules.identity.models import User
from modules.platform.models import StaffMFA


class Command(BaseCommand):
    help = "Hapus perangkat MFA staf platform; staf wajib mendaftar ulang saat login berikutnya."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--reason", required=True, help="Alasan reset (dicatat di audit).")

    def handle(self, *args, **options):
        user = User.objects.filter(email__iexact=options["email"], is_staff=True).first()
        if user is None:
            raise CommandError("Staf platform tidak ditemukan.")
        deleted, _ = StaffMFA.objects.filter(user=user).delete()
        log_event(action="platform.mfa.reset", actor=None, object_type="user", object_id=user.pk, changes={"reason": options["reason"][:240], "count": deleted})
        self.stdout.write(f"MFA {user.email} direset ({deleted} perangkat).")
