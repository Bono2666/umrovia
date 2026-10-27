#!/usr/bin/env bash
# Drill restore Umrovia (Spec §13: tested restore bulanan; Ops gate S19).
#
# Mendekripsi backup, memeriksa checksum, me-restore ke database BARU (tidak pernah
# menimpa database sumber), memastikan migrasi lengkap, lalu menjalankan
# `verify_integrity` dan (opsional) membandingkan jumlah baris dengan sumber.
#
# Pemakaian:
#   BACKUP_PASSPHRASE=... ADMIN_DATABASE_URL=postgres://user@host:5432/postgres \
#     ./restore_drill.sh /srv/backups/umrovia-<stamp>.tar.enc [nama_db_target]
# Opsional: SOURCE_DATABASE_URL (bandingkan hitungan), KEEP=1 (jangan hapus DB target),
#           PYTHON (bawaan ../../.venv/bin/python), REPORT (path laporan JSON).
set -euo pipefail

ARCHIVE="${1:?Path backup .tar.enc wajib}"
TARGET="${2:-umrovia_restore_drill_$(date -u +%Y%m%d%H%M%S)}"
: "${BACKUP_PASSPHRASE:?Set BACKUP_PASSPHRASE}"
: "${ADMIN_DATABASE_URL:?Set ADMIN_DATABASE_URL (koneksi admin untuk membuat database target)}"
HERE="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$HERE/../../backend"
PYTHON="${PYTHON:-$HERE/../../.venv/bin/python}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
START=$(date +%s)
TARGET_URL="${ADMIN_DATABASE_URL%/*}/$TARGET"

case "$TARGET" in
  *[!a-z0-9_]*) echo "nama database target hanya huruf kecil, angka, _"; exit 2 ;;
esac

if [ -f "$ARCHIVE.sha256" ]; then shasum -a 256 -c "$ARCHIVE.sha256" > /dev/null && echo "drill: checksum arsip OK"; fi
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:BACKUP_PASSPHRASE -in "$ARCHIVE" | tar xf - -C "$WORK"
( cd "$WORK" && shasum -a 256 -c SHA256SUMS > /dev/null ) && echo "drill: checksum isi OK"
echo "drill: media $(tar tzf "$WORK/media.tgz" | grep -vc '/$') berkas"

psql "$ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 -qc "CREATE DATABASE $TARGET"
pg_restore --no-owner --no-privileges --exit-on-error -d "$TARGET_URL" "$WORK/db.dump"
echo "drill: restore ke $TARGET selesai"

cd "$BACKEND"
DATABASE_URL="$TARGET_URL" "$PYTHON" manage.py migrate --check > /dev/null && echo "drill: skema lengkap (tidak ada migrasi tertunda)"
DATABASE_URL="$TARGET_URL" "$PYTHON" manage.py verify_integrity --json > "$WORK/restored.json" || true
STATUS=$("$PYTHON" -c "import json,sys; print('OK' if json.load(open(sys.argv[1]))['ok'] else 'GAGAL')" "$WORK/restored.json")
echo "drill: integritas hasil restore = $STATUS"

DIFF="tidak dibandingkan"
if [ -n "${SOURCE_DATABASE_URL:-}" ]; then
  DATABASE_URL="$SOURCE_DATABASE_URL" "$PYTHON" manage.py verify_integrity --json > "$WORK/source.json" || true
  DIFF=$("$PYTHON" - "$WORK/source.json" "$WORK/restored.json" <<'PY'
import json, sys
src, dst = (json.load(open(p))["counts"] for p in sys.argv[1:3])
bad = {k: (src.get(k), dst.get(k)) for k in sorted(set(src) | set(dst)) if src.get(k) != dst.get(k)}
print("sama persis (%d tabel, %d baris)" % (len(src), sum(src.values())) if not bad else "BERBEDA: %s" % bad)
PY
)
fi
echo "drill: hitungan baris sumber vs restore: $DIFF"
ELAPSED=$(( $(date +%s) - START ))
echo "drill: durasi ${ELAPSED} detik (target RTO pilot ≤ 8 jam)"

if [ -n "${REPORT:-}" ]; then
  "$PYTHON" - "$WORK/restored.json" "$REPORT" "$ARCHIVE" "$TARGET" "$ELAPSED" "$DIFF" <<'PY'
import json, sys
result = json.load(open(sys.argv[1]))
json.dump({"archive": sys.argv[3].rsplit("/", 1)[-1], "target_db": sys.argv[4], "seconds": int(sys.argv[5]), "count_comparison": sys.argv[6],
           "integrity_ok": result["ok"], "checks": result["checks"], "tables": len(result["counts"]), "rows": sum(result["counts"].values())},
          open(sys.argv[2], "w"), ensure_ascii=False, indent=2)
PY
  echo "drill: laporan $REPORT"
fi

if [ "${KEEP:-0}" != "1" ]; then
  psql "$ADMIN_DATABASE_URL" -qc "DROP DATABASE $TARGET" && echo "drill: database target dihapus"
fi
[ "$STATUS" = "OK" ] && [[ "$DIFF" != BERBEDA* ]]
