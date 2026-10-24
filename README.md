# Umrovia — SaaS Manajemen Travel Umroh & Haji

Platform SaaS multi-tenant untuk travel Umroh & Haji: pay-per-jamaah Rp50.000 per
booking-jamaah setelah DP terverifikasi, gratis bulanan/setup, free trial 30 hari.

**Dokumen proyek (sumber kebenaran — jangan dimodifikasi):**

- `docs/PRD_Umrovia_SaaS_v3_5_Development_Roadmap.md` — ruang lingkup, bisnis, milestone
- `docs/PRODUCT_SPEC_Umrovia_SaaS_v1_2_Development_Plan.md` — modul, DB §5, API §8, test §14
- `docs/DEVELOPMENT_ROADMAP_Umrovia_v1_0.md` — sprint S01–S19, fase F01–F08

Status sprint: `docs/development/SPRINT_TRACKING.md` · ADR: `docs/adr/`

## Arsitektur (Spec §19.2)

```
umrovia/
├── apps/                  # Next.js frontends (web=marketing, dashboard=tenant, admin=platform)
│   └── dashboard/         # app.umrovia.com — workspace travel
├── backend/               # Django + DRF modular monolith
│   ├── config/            # settings (base/local/production), urls, wsgi/asgi
│   ├── modules/           # identity, tenants, (…: pilgrims, bookings, payments, dst.)
│   ├── common/            # shared base model, middleware (request-id), utils
│   └── tests/             # pytest suite
├── infra/                 # docker, deployment, telemetry
├── docs/                  # PRD, Product Spec, Roadmap, ADR, tracking
├── legacy/                # aplikasi Django v0 (referensi, DIHAPUS setelah F06)
└── docker-compose.yml
```

Stack: Python 3.11+/Django 5.2 LTS/Django REST Framework · PostgreSQL 17+ (RLS) ·
Redis + Celery (mulai F06/F07) · Next.js + TypeScript · S3-compatible storage.

## Bootstrap lokal

```bash
# 1. Backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.lock -r backend/requirements-dev.txt

# 2. Environment
cp .env.example .env          # isi DATABASE_URL, SECRET_KEY, dll.

# 3. Database (butuh PostgreSQL berjalan; lokal bisa Homebrew/managed)
createdb umrovia
export $(grep -v '^#' .env | xargs)
cd backend && python manage.py migrate && cd ..

# 4. Jalankan
cd backend && python manage.py runserver 8000      # API: http://localhost:8000/api/v1/health/
cd apps/dashboard && npm install && npm run dev    # Web: http://localhost:3000

# 5. Tests & lint
cd backend && pytest && ruff check .
cd apps/dashboard && npm run lint
```

Docker (butuh Docker Desktop/Engine): `docker compose up --build` → api:8000, web:3000, db:5432, redis:6379.

### Email formulir kontak marketing

Pesan kontak disimpan di database dan notifikasinya ditujukan ke
`CONTACT_RECIPIENT_EMAIL` (default: `bonoworxx@gmail.com`). Reply-To memakai
alamat pengunjung; alamat pengirim memakai `DEFAULT_FROM_EMAIL` yang diizinkan
oleh penyedia email, bukan alamat pengunjung.

Backend email default adalah **console**: email hanya ditampilkan pada log lokal,
tidak dikirim ke inbox. Untuk pengiriman nyata, isi `.env` dengan konfigurasi
penyedia SMTP, lalu jalankan ulang container API:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.penyedia-anda.example
EMAIL_PORT=587
EMAIL_HOST_USER=akun-smtp
EMAIL_HOST_PASSWORD=isi-secret-di-env-lokal
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
DEFAULT_FROM_EMAIL=Umrovia <alamat-pengirim-terverifikasi@example.com>
CONTACT_RECIPIENT_EMAIL=bonoworxx@gmail.com
```

`docker compose up -d --no-deps --build api` menerapkan konfigurasi tersebut.
Jangan commit kredensial SMTP. Jika pengiriman gagal, pesan tetap tersimpan dan
dapat diperiksa melalui Django admin menggunakan nomor referensinya. Pengiriman
belum memiliki antrean retry otomatis; periksa log dan pesan tersimpan bila SMTP
bermasalah.

## Aturan branching & kualitas (Roadmap §1)

- `main` selalu green; semua pekerjaan lewat branch `sprint/<sprint>-<topik>` atau `feat/<topik>`.
- Setiap issue memakai status `TODO / IN_PROGRESS / BLOCKED / IN_REVIEW / DONE` di
  `docs/development/SPRINT_TRACKING.md` dan ditautkan ke commit/PR.
- Definition of Done per issue (Roadmap §6): acceptance PRD/Spec terpenuhi, test happy path +
  invalid input + authorization + multi-tenant otomatis, migrasi reproducible, OpenAPI +
  changelog, tanpa issue security critical/high, logging tanpa PII/secrets.
- Commit message: `<area>: <deskripsi>` (contoh `tenants: tambah model Tenant/Membership`).

## Legacy

`legacy/` adalah aplikasi Django v0 (MySQL + template Soft UI) hasil konversi awal —
dipertahankan sebagai referensi logika bisnis & demo interim. Jangan tambah fitur baru di sana.
