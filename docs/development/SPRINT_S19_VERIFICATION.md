# Verifikasi Sprint S19

Tanggal: 27 Oktober 2026. Branch: `sprint/s19-release-readiness`.
Status: pekerjaan rekayasa selesai; gate "MVP release gates signed" **belum
ditandatangani** — lihat [GO_LIVE_CHECKLIST](../release/GO_LIVE_CHECKLIST.md).

## Test otomatis

- Suite backend lengkap: **434/434 lulus** dengan dependensi yang sudah
  dinaikkan, termasuk 16 kasus baru: `test_release_security.py` (10),
  `test_performance.py` (2), `test_e2e_mvp.py` (1), `test_uat_traceability.py` (2),
  regresi penjadwal worker (1).
- Ruff (termasuk aturan S/bandit pada kode aplikasi), ESLint, TypeScript,
  `makemigrations --check` bersih; `next build` produksi berhasil.

## Keamanan

- `pip-audit`: 14 kerentanan pada `cryptography` 46.0.7, `djangorestframework`
  3.16.1 dan `pytest` 8.4.2 → dinaikkan ke 50.0.2, 3.18.3, 9.1.1; kini
  "No known vulnerabilities". `npm audit --omit=dev`: 0.
- SAST: satu temuan `S310` (urllib Midtrans) → ditambah penjaga allowlist
  host HTTPS Midtrans (cegah SSRF/skema lain).
- `check --deploy` dengan setting produksi: hanya `security.W004` (HSTS
  bertahap, disengaja); test juga membuktikan kunci lemah tertangkap (W009)
  dan setting produksi menolak start tanpa SECRET_KEY/PII key/ALLOWED_HOSTS.
- Host asing 400, CSRF wajib untuk tulis berbasis sesi, CORS hanya origin
  terdaftar, header nosniff/DENY/same-origin, log seluruh alur DP/ekspor
  tanpa nama/NIK/paspor/email/telepon jamaah.

## Integritas, backup & restore

- `manage.py verify_integrity` (read-only): RLS ENABLE+FORCE 33/33 tabel
  tenant, rantai ledger & saldo wallet, charge ↔ debit, invoice ↔ pembayaran,
  checksum PDF, kursi, antrean email; mendeteksi invoice yang dirusak.
  Dijadwalkan harian di worker.
- Drill pada database uji bervolume (24 keberangkatan, 720 jamaah, 240
  booking, 120 DP): backup terenkripsi 9,3 MB → restore ke database baru →
  checksum arsip & isi OK, tanpa migrasi tertunda, integritas OK (RLS ikut
  ter-restore), hitungan **sama persis 28 tabel / 7.812 baris**, 10 detik.
  Passphrase salah gagal sebelum database dibuat.

## Uji beban & konkurensi

`infra/load/load_test.py` (stdlib) terhadap gunicorn 4 worker, `DEBUG=False`:

| Tahap | Pengguna paralel | Request | Galat | RPS | p95 |
|---|---:|---:|---:|---:|---:|
| Awal | 10 | 512 | 0 | 17,1 | 1.628 ms |
| Setelah N+1 diperbaiki | 10 | 1.034 | 0 | 34,5 | 617 ms |
| Final (paginasi seperti UI) | 10 | 1.798 | 0 | 59,9 | **328 ms** |
| Final | 4 | 1.731 | 0 | 57,7 | 225 ms |

Semua endpoint p95 < 500 ms pada tahap final (tertinggi: laporan keuangan
463 ms). Perebutan kursi terakhir: 20 permintaan serentak → tepat 1 berhasil,
19 ditolak 400, kursi terisi 1.

Perbaikan dari uji beban:
- `/payments` 368 → 11 query (prefetch alokasi & peserta, tanpa PDF),
  `/invoices` 208 → 8 query (tenant di-join, tanpa PDF); dijaga test jumlah
  query konstan.
- Paginasi opt-in `?page=` (50/halaman, `page_size` ≤ 100) untuk booking,
  invoice, pembayaran; halaman Booking/Invoice/Pembayaran memakai paginasi
  server; sebelumnya daftar terpotong diam-diam di 200 baris.
- Pilihan invoice di form Pembayaran: hanya invoice terbuka + pencarian
  server (nomor, kode booking, pelanggan); ringkasan dashboard cukup 1 baris.

## Staging

`docker-compose.staging.yml` (setting produksi, Caddy TLS, host app/admin/api)
dinyalakan dengan secret sementara: smoke test **15/15** (health, header,
HTTP→HTTPS, Host asing 421 & tanpa sertifikat ditolak, CORS, cookie Secure,
host admin → /platform, endpoint terlindungi). Browser: login di host app,
cookie sesi Secure+HttpOnly host-only di api, POST lintas host dengan CSRF
berhasil, host admin → login → gerbang MFA. Temuan: Caddy menjawab 200 kosong
untuk Host ≠ SNI → `strict_sni_host` diaktifkan. Stack staging uji dihapus
setelah verifikasi.

## Docker lokal

Setelah rebuild, `/api/v1/health/` melaporkan database, cache, worker dan
antrean email `ok`; `verify_integrity` pada data lokal pengguna: semua cek OK.

Temuan saat verifikasi Docker: penjadwal worker menginisialisasi waktu
terakhir dengan `0` sedangkan `time.monotonic()` dihitung sejak mesin
menyala, sehingga job ber-interval lebih panjang dari uptime mesin (harian
`verify_integrity`, juga job per jam pada server yang baru reboot) tidak
berjalan saat worker start. Diperbaiki (`-inf`) dengan test regresi
`test_worker_runs_every_scheduled_job_on_start`.

## Batas S19

Butir ⛔/📝 di GO_LIVE_CHECKLIST (domain & TLS publik, secret manager,
monitoring/alerting, backup terjadwal offsite, bucket media, email
transaksional produksi, Midtrans produksi, antimalware, MFA keuangan tenant,
UAT manual, hukum/UU PDP) membutuhkan infrastruktur atau keputusan di luar
repositori. OpenAPI: 47 view belum punya skema respons eksplisit.
