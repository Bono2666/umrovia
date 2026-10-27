#!/usr/bin/env bash
# Backup terenkripsi Umrovia (Spec §13 Backup: harian, terenkripsi, privat; S19).
#
# Isi: pg_dump format custom (termasuk RLS + policy) + arsip media (dokumen jamaah)
# + manifest SHA-256, lalu dienkripsi AES-256 (openssl, PBKDF2 200k iterasi).
#
# Pemakaian:
#   BACKUP_PASSPHRASE=... DATABASE_URL=postgres://... MEDIA_DIR=/path BACKUP_DIR=/srv/backups ./backup.sh
#   BACKUP_SOURCE=compose BACKUP_PASSPHRASE=... BACKUP_DIR=... ./backup.sh   # stack docker compose lokal
# Variabel opsional: RETENTION_DAYS (bawaan 14), COMPOSE_FILE, COMPOSE_PROJECT_NAME, COMPOSE_ENV_FILES
# (VPS produksi: lihat docs/runbooks/FIRST_DEPLOY_VPS.md).
set -euo pipefail

: "${BACKUP_PASSPHRASE:?Set BACKUP_PASSPHRASE (simpan di secret manager, bukan di repo)}"
: "${BACKUP_DIR:?Set BACKUP_DIR (penyimpanan privat terenkripsi)}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
SOURCE="${BACKUP_SOURCE:-url}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
umask 077
mkdir -p "$BACKUP_DIR"

echo "backup: database ($SOURCE)"
if [ "$SOURCE" = "compose" ]; then
  docker compose exec -T db sh -c 'pg_dump -Fc --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$WORK/db.dump"
  echo "backup: media (compose)"
  docker compose exec -T api sh -c 'tar czf - -C /backend/media . 2>/dev/null || tar czf - --files-from /dev/null' > "$WORK/media.tgz"
else
  : "${DATABASE_URL:?Set DATABASE_URL}"
  pg_dump -Fc --no-owner --no-privileges "$DATABASE_URL" > "$WORK/db.dump"
  if [ -n "${MEDIA_DIR:-}" ] && [ -d "$MEDIA_DIR" ]; then
    echo "backup: media ($MEDIA_DIR)"
    tar czf "$WORK/media.tgz" -C "$MEDIA_DIR" .
  else
    tar czf "$WORK/media.tgz" --files-from /dev/null
  fi
fi

# Dump harus terbaca sebelum disimpan. Mode compose memakai pg_restore di container db,
# karena host VPS tidak memasang klien Postgres (versinya juga harus sama dengan server).
if [ "$SOURCE" = "compose" ]; then
  docker compose exec -T db pg_restore --list < "$WORK/db.dump" > /dev/null
else
  pg_restore --list "$WORK/db.dump" > /dev/null
fi
( cd "$WORK" && shasum -a 256 db.dump media.tgz > SHA256SUMS && printf 'created_at=%s\nsource=%s\n' "$STAMP" "$SOURCE" > MANIFEST )

OUT="$BACKUP_DIR/umrovia-$STAMP.tar.enc"
tar cf - -C "$WORK" db.dump media.tgz SHA256SUMS MANIFEST \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:BACKUP_PASSPHRASE -out "$OUT"
shasum -a 256 "$OUT" > "$OUT.sha256"
echo "backup: tersimpan $OUT ($(du -h "$OUT" | cut -f1))"

find "$BACKUP_DIR" -name 'umrovia-*.tar.enc*' -type f -mtime +"$RETENTION_DAYS" -print -delete | sed 's/^/backup: retensi hapus /'
