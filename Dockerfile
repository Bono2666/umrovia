# =============================================================================
# Dockerfile - aplikasi Django Umrovia
# Dipakai untuk build image (docker build -t umrovia .) di mesin yang
# mendukung Docker. Deployment ke shared hosting TIDAK memakai
# Docker (tidak ada root/daemon di sana) -> lihat deploy/deploy.sh.
# =============================================================================
FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# dependensi build untuk pillow/lxml/pymysql
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential pkg-config default-libmysqlclient-dev \
        libjpeg-dev zlib1g-dev libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt gunicorn whitenoise

COPY . .

RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

# migrate saat container start (idempoten), lalu jalankan gunicorn
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120"]
