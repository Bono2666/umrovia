"""Retry pending SaaS charges FIFO per tenant; scheduling belongs to S16."""
from django.core.management.base import BaseCommand, CommandError

from modules.billing.services import lock_wallet, settle_pending_charges
from modules.tenants.models import Tenant
from modules.wallet.services import platform_tenant_context


class Command(BaseCommand):
    help = "Post pending SaaS charges when wallet balance allows; never overdraws."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="Optional tenant slug; default all production tenants")

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(environments__environment="production", environments__state="ACTIVE")
        if options["tenant"]:
            tenants = tenants.filter(slug=options["tenant"])
            if not tenants.exists():
                raise CommandError("Travel produksi tidak ditemukan.")
        totals = {"posted": 0, "pending": 0, "voided": 0}
        for tenant in tenants.iterator():
            with platform_tenant_context(tenant.pk) as scoped:
                result = settle_pending_charges(lock_wallet(scoped))
            for key in totals:
                totals[key] += result[key]
        self.stdout.write(" ".join(f"{key}={value}" for key, value in totals.items()))
