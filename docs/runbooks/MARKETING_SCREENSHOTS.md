# Runbook — Screenshot halaman marketing

Gambar di `apps/dashboard/public/marketing/*.webp` adalah tangkapan layar aplikasi
Umrovia sungguhan, tetapi **datanya fiktif**: travel "Amanah Haramain Tour" yang diisi
oleh `infra/marketing/seed_demo.py` ke database lokal. Jangan pernah memotret data
produksi; nama, NIK, paspor, dan telepon jamaah sungguhan tidak boleh muncul di situs.

Perbarui gambar bila tampilan halaman yang dipotret berubah.

| Berkas | Sumber di aplikasi |
|---|---|
| `ringkasan.webp` (pita gelap) | Ringkasan workspace |
| `kanal-leads.webp` | Leads — daftar lead |
| `profil-jamaah.webp` | Jamaah — panel Detail |
| `termin.webp` | Invoice — dibayar sebagian + rincian |
| `kuitansi.webp` | PDF kuitansi pelunasan |
| `kelengkapan-berkas.webp` | Manifest — status dokumen & bayar per jamaah |
| `daftar-jamaah.webp` | Jamaah — daftar |
| `kuota-jadwal.webp` | Ringkasan — Keberangkatan terdekat |
| `manifest-final.webp` | Manifest — roster & ekspor |

## Langkah

Prasyarat laptop: Postgres lokal, Chrome, Python dengan Playwright, Pillow, PyMuPDF.

```bash
cd backend
export DATABASE_URL=postgres://$USER@localhost:5432/umrovia_demo DEBUG=True \
  EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend \
  WALLET_MANUAL_BANK_NAME="BANK PLATFORM" WALLET_MANUAL_ACCOUNT_NAME="PT Umrovia" \
  WALLET_MANUAL_ACCOUNT_NUMBER=000123456
unset MIDTRANS_SERVER_KEY MIDTRANS_IS_PRODUCTION

# 1. Database demo kosong + data fiktif (tanggal disusun untuk akhir Oktober 2026)
dropdb -h localhost --if-exists umrovia_demo && createdb -h localhost umrovia_demo
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py shell < ../infra/marketing/seed_demo.py

# 2. Jalankan API & web lokal (dua terminal)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend ../.venv/bin/python manage.py runserver 8000
cd ../apps/dashboard && npx next dev -p 3000

# 3. Potret → langsung ditulis sebagai WebP ke public/marketing/
python3 infra/marketing/capture.py
```

Periksa semua gambar sebelum commit. Bila tanggal demo sudah lewat (follow-up tampil
"terlambat", keberangkatan sudah berangkat), geser tanggal di `seed_demo.py` dulu.
