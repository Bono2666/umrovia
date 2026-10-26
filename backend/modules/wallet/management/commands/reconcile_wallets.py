"""Daily reconciliation, safe expiry and pending-charge retry; scheduling belongs to S16."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from modules.audit.services import log_event
from modules.billing.services import settle_pending_charges
from modules.tenants.models import Tenant
from modules.wallet import midtrans
from modules.wallet.models import WalletTopup
from modules.wallet.services import platform_tenant_context, reconcile_wallet, sync_gateway_topups


class Command(BaseCommand):
    help = "Reconcile SaaS wallets without rewriting balances; exit nonzero on mismatch."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", help="Optional tenant slug; default all production tenants")

    def handle(self, *args, **options):
        tenants = Tenant.objects.filter(environments__environment="production", environments__state="ACTIVE")
        if options["tenant"]:
            tenants = tenants.filter(slug=options["tenant"])
            if not tenants.exists():
                raise CommandError("Travel produksi tidak ditemukan.")
        checked = 0
        mismatches = 0
        for tenant in tenants.iterator():
            # Missed Midtrans webhooks: re-read open orders (network, no locks held).
            if midtrans.configured():
                sync_gateway_topups(tenant.pk)
            with platform_tenant_context(tenant.pk):
                # This retains the wallet lock through the outer transaction,
                # keeping the same wallet -> top-up order as submission/settlement.
                result = reconcile_wallet()
                with transaction.atomic():
                    # Submission obtains a top-up row lock too. Never expire
                    # PENDING evidence: funds may already be in transit.
                    # Midtrans orders follow the gateway status (sync above), not this timer.
                    for topup in WalletTopup.objects.select_for_update().filter(provider="manual", status="CREATED", expires_at__lte=timezone.now()):
                        topup.status = "EXPIRED"
                        topup.save(update_fields=["status", "updated_at"])
                        log_event(action="wallet.topup.expired", tenant=tenant, object_type="wallet_topup", object_id=topup.pk)
                if result:
                    checked += 1
                    mismatches += not result.consistent
                    if result.consistent:
                        # Spec §11 pending_charge_retry after reconciliation; a
                        # mismatched wallet is reviewed before any new debit.
                        settle_pending_charges(result.wallet)
        self.stdout.write(f"wallets={checked} mismatches={mismatches}")
        if mismatches:
            raise CommandError("Rekonsiliasi menemukan mismatch; tinjau tanpa mengedit ledger.")
