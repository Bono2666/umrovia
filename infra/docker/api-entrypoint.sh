#!/bin/sh
# Menunggu DB siap, migrate, lalu jalankan server (dev/staging).
set -e

echo "api: menunggu database..."
python - <<'PY'
import time
import dj_database_url
import psycopg

dsn = dj_database_url.config(conn_max_age=0)
for attempt in range(30):
    try:
        with psycopg.connect(dsn.dsn) as conn:
            conn.execute("SELECT 1")
        break
    except psycopg.OperationalError:
        time.sleep(2)
else:
    raise SystemExit("database tidak tersedia setelah 60 detik")
print("api: database siap")
PY

python manage.py migrate --noinput
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --access-logfile - --error-logfile -
