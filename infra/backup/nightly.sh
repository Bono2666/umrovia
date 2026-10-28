#!/usr/bin/env bash
# Job harian VPS (cron 01:00 WIB): backup terenkripsi → salinan offsite → laporan ke Healthchecks.
#
#   0 18 * * * /srv/umrovia/infra/backup/nightly.sh >> /srv/backups/backup.log 2>&1
#
# Konfigurasi di /etc/umrovia/backup.env (atau ENV_FILE): variabel backup.sh, ditambah
#   OFFSITE_REMOTE  remote rclone tujuan salinan, mis. neo:umrovia-backups (kosong = tanpa offsite)
#   HC_PING_URL     URL ping Healthchecks.io, mis. https://hc-ping.com/<uuid> (kosong = tanpa laporan)
# Gagal di langkah mana pun → ping /fail, sehingga Healthchecks mengirim peringatan.
# Tidak ada ping sama sekali (cron/VPS mati) → peringatan setelah periode + grace terlewati.
set -uo pipefail

ENV_FILE="${ENV_FILE:-/etc/umrovia/backup.env}"
set -a
# shellcheck source=/dev/null
. "$ENV_FILE"
set +a
cd "$(dirname "$0")/../.." || exit 1

ping() {
  [ -n "${HC_PING_URL:-}" ] || return 0
  curl -fsS -m 10 --retry 3 -o /dev/null "$HC_PING_URL$1" || echo "nightly: ping Healthchecks$1 gagal"
}

offsite() {
  [ -n "${OFFSITE_REMOTE:-}" ] || return 0
  rclone copy "$BACKUP_DIR" "$OFFSITE_REMOTE" --include 'umrovia-*' && echo "offsite: tersalin ke $OFFSITE_REMOTE"
}

echo "nightly: mulai $(date -u +%FT%TZ)"
ping /start
if infra/backup/backup.sh && offsite; then
  ping ""
  echo "nightly: selesai"
else
  echo "nightly: GAGAL"
  ping /fail
  exit 1
fi
