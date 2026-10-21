#!/usr/bin/env bash
# =============================================================================
# Deploy aplikasi Umrovia ke shared hosting ksisolusi.com (Passenger)
# Pemakaian : ./deploy/deploy.sh [user@host]
# Server    : TIDAK punya rsync, jadi dipakai tar-over-SSH.
# =============================================================================
set -euo pipefail

REMOTE="${1:-ksisolusi.com}"
APP_DIR="/home/ksis7654/apps/umrovia"
VENV="/home/ksis7654/virtualenv/apps/umrovia/3.10"
DOCROOT="/home/ksis7654/public_html/umrovia"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> [1/6] Kirim source ke ${REMOTE}:${APP_DIR}"
tar czf - \
  --exclude='./venv' --exclude='./bin' --exclude='./lib' --exclude='./pyvenv.cfg' \
  --exclude='./.git' --exclude='*/__pycache__' --exclude='*.pyc' --exclude='.DS_Store' \
  --exclude='./._*' --exclude='*/._*' \
  --exclude='./.idea' --exclude='./.vscode' --exclude='./stderr.log' --exclude='./.env' \
  --exclude='./apps/media' --exclude='./apps/staticfiles' \
  -C "$SRC_DIR" . | ssh "$REMOTE" "set -e
    cd '$APP_DIR'
    # bersihkan isi lama; simpan .git/tmp/public/passenger_wsgi/stderr.log
    find . -mindepth 1 -maxdepth 1 \
      ! -name .git ! -name tmp ! -name public \
      ! -name passenger_wsgi.py ! -name stderr.log \
      -exec rm -rf {} +
    tar xzf -
    find . -name '._*' -delete
    # media permanen ada di docroot -> jadikan symlink dari app
    if [ ! -L apps/media ]; then rm -rf apps/media; ln -s '$DOCROOT/apps/media' apps/media; fi
    [ -f passenger_wsgi.py ] || cp -f deploy/passenger_wsgi.py passenger_wsgi.py
    echo '    transfer OK'"

echo "==> [2/6] Sinkronkan dependensi"
ssh "$REMOTE" "$VENV/bin/pip install -q -r '$APP_DIR/requirements.txt' && echo '    pip OK'"

echo "==> [3/6] Siapkan symlink static di docroot"
ssh "$REMOTE" "set -e
  cd '$DOCROOT'
  # -L dulu: symlink lama yang targetnya (staticfiles) belum dibuat ulang
  # tetap dianggap sah, jangan dibuat tumpang tindih
  [ -L apps/static ] || [ -e apps/static ] || ln -s '$APP_DIR/apps/staticfiles' apps/static
  [ -L static ] || [ -e static ] || ln -s '$APP_DIR/apps/staticfiles' static
  echo '    symlink OK'"

echo "==> [4/6] collectstatic (--clear: buang hasil lama agar tidak ada aset basi)"
ssh "$REMOTE" "$VENV/bin/python '$APP_DIR/manage.py' collectstatic --noinput --clear | tail -2"

echo "==> [5/6] Restart Passenger"
ssh "$REMOTE" "mkdir -p '$APP_DIR/tmp' && touch '$APP_DIR/tmp/restart.txt' && echo '    restart OK'"

echo "==> [6/6] Verifikasi"
curl -sS -o /dev/null -w "    https://umrovia.ksisolusi.com/ -> %{http_code}\n" --max-time 45 \
  https://umrovia.ksisolusi.com/ || true

echo "==> Deploy selesai."
