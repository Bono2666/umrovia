"""Buat/promosikan staf platform dengan satu peran (least privilege). MFA didaftarkan saat login pertama."""
import os
from getpass import getpass

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from modules.audit.services import log_event
from modules.identity.models import User, UserStatus
from modules.tenants.models import TenantMembership

ROLES = ["Platform Super Admin", "Platform Billing", "Platform Support"]


class Command(BaseCommand):
    help = "Buat staf platform (password dari env PLATFORM_STAFF_PASSWORD atau prompt)."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--role", choices=ROLES, required=True)
        parser.add_argument("--name", default="")

    def handle(self, *args, **options):
        user = User.objects.filter(email__iexact=options["email"]).first()
        if user is None:
            password = os.environ.get("PLATFORM_STAFF_PASSWORD") or getpass("Password: ")
            if len(password) < 12:
                raise CommandError("Password staf platform minimal 12 karakter.")
            user = User.objects.create_user(email=options["email"], password=password, full_name=options["name"], status=UserStatus.ACTIVE, email_verified_at=timezone.now())
        if TenantMembership.objects.without_tenant_guard().filter(user=user).exists():
            self.stderr.write("Peringatan: akun ini juga anggota workspace travel; sebaiknya staf platform memakai akun terpisah.")
        user.is_staff = True
        user.save(update_fields=["is_staff", "updated_at"])
        user.groups.add(Group.objects.get(name=options["role"]))
        log_event(action="platform.staff.granted", actor=None, object_type="user", object_id=user.pk, changes={"role": options["role"]})
        self.stdout.write(f"{user.email} → {options['role']}. Login di /login lalu daftarkan MFA.")
