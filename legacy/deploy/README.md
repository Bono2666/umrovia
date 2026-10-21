# Deployment - Umrovia

Target: **https://umrovia.ksisolusi.com** (shared hosting `ksisolusi.com`,
cPanel + CloudLinux + LiteSpeed, tanpa Docker/root).

> Server tujuan **tidak mendukung Docker** (tidak ada daemon, tidak ada
> `sudo`/root, terisolasi CageFS). Karena itu deployment memakai mekanisme
> bawaan hosting: **virtualenv Python 3.10 + CloudLinux Passenger**.
> `Dockerfile` dan `docker-compose.yml` tetap disediakan untuk menjalankan
> aplikasi di mesin yang mendukung Docker (VPS lokal, dsb).

## Peta deployment di server

| Komponen | Lokasi |
|---|---|
| Source aplikasi | `~/apps/umrovia` (PassengerAppRoot) |
| Virtualenv Python 3.10 | `~/virtualenv/apps/umrovia/3.10` |
| Docroot subdomain | `~/public_html/umrovia` |
| Konfigurasi (Passenger + env) | `~/public_html/umrovia/.htaccess` |
| Media (permanen, di luar source) | `~/public_html/umrovia/apps/media` ← symlink dari `~/apps/umrovia/apps/media` |
| Static hasil `collectstatic` | `~/apps/umrovia/apps/staticfiles` → disajikan via symlink `public_html/umrovia/apps/static` dan `public_html/umrovia/static` |
| Database | MariaDB `ksis7654_umrovia` (user & password di `.htaccess` sebagai `SetEnv DB_*`) |

## Cara deploy ulang

```bash
./deploy/deploy.sh              # default host: ksisolusi.com (lihat ~/.ssh/config)
./deploy/deploy.sh user@host    # host lain
```

Alur skrip: kirim source (tar-over-SSH, server tidak punya `rsync`) →
`pip install -r requirements.txt` → pasang symlink static → `collectstatic` →
`touch tmp/restart.txt` (restart Passenger) → cek HTTP.

## Konfigurasi environment

Dibaca `core/settings.py` melalui `os.environ` (diisi `SetEnv` di `.htaccess`):

- `ALLOWED_HOSTS`, `DEBUG`, `SECRET_KEY`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
- `DATABASE_URL` (opsional, menimpa `DB_*` bila diisi)

> **PENTING:** setiap kali `SetEnv` di `.htaccess` diubah, jalankan
> `touch ~/apps/umrovia/tmp/restart.txt` — Passenger membaca env saat proses
> di-spawn, jadi perubahan tidak aktif sampai restart.

## Perintah operasional (via SSH)

```bash
ssh ksisolusi.com
cd ~/apps/umrovia
export DB_NAME=... DB_USER=... DB_PASSWORD=...       # ambil dari .htaccess
V=~/virtualenv/apps/umrovia/3.10/bin/python

$V manage.py migrate         # terapkan migrasi baru
$V manage.py collectstatic --noinput
$V manage.py check --deploy  # cek setting produksi
touch tmp/restart.txt        # restart aplikasi
```

## Catatan penting

- **Migrasi `apps.0029`** diperbaiki: `AlterUniqueTogether` dipindah *sebelum*
  `RemoveField(grade/subject)`, karena versi lama gagal pada database baru
  (`Key column 'grade_id' doesn't exist in table` / `Duplicate column name`).
- **Model `User.save()`** memanggil `get_current_user().user_id` yang `None`
  di luar konteks request → pembuatan user via shell/`createsuperuser`
  gagal. Gunakan `User.objects.bulk_create([...])` untuk membuat user CLI.
- **Docker**: `docker compose up -d --build` (butuh `.env` berisi
  `SECRET_KEY`, `DB_PASSWORD`, dsb — salin dari `deploy/env.example`
  bila dibuat). Mode ini hanya untuk mesin bersertifikat Docker.
- Menyalakan `DEBUG` sementara: ubah `SetEnv DEBUG "True"` di `.htaccess`
  lalu `touch ~/apps/umrovia/tmp/restart.txt`. **Kembalikan ke `"False"`
  setelah selesai.**
