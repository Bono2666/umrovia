"""Job `backup_validation` / `reconciliation_daily` (Spec §11.2): cek integritas read-only; exit 1 bila gagal."""
import json

from django.core.management.base import BaseCommand, CommandError

from modules.platform import integrity


class Command(BaseCommand):
    help = "Periksa RLS, ledger wallet, invoice, checksum PDF, kursi dan antrean (tanpa mengubah data)."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="Cetak hasil lengkap sebagai JSON (untuk drill restore).")

    def handle(self, *args, **options):
        result = integrity.run()
        if options["json"]:
            self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            for check in result["checks"]:
                self.stdout.write(f"[{'OK' if check['ok'] else 'GAGAL'}] {check['name']}" + (f" — {check['detail']}" if check["detail"] else ""))
            self.stdout.write(f"baris: {sum(result['counts'].values())} di {len(result['counts'])} tabel")
        if not result["ok"]:
            raise CommandError("Integritas data gagal; tinjau tanpa mengedit ledger.")
