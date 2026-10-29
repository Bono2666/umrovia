# Runbook — Deploy, staging & rollback

## Lingkungan

| Lingkungan | Cara | Aturan |
|---|---|---|
| Lokal | `docker compose up -d` | Data dummy, gateway sandbox/manual |
| Staging | `docker-compose.staging.yml` + `.env.staging` | Setting produksi, host sendiri, Midtrans **sandbox**, database terpisah |
| Produksi | Sama dengan staging, secret produksi | Persetujuan rilis (GO_LIVE_CHECKLIST), backup sebelum deploy |

## Deploy staging/produksi

Pemasangan pertama di VPS (bootstrap server, sertifikat, akun pertama, backup
terjadwal): [FIRST_DEPLOY_VPS.md](FIRST_DEPLOY_VPS.md).

1. CI hijau (lint, SAST, pip-audit, npm audit, deploy check, test, build).
2. Backup sebelum deploy: `infra/backup/backup.sh`.
3. `docker compose -f docker-compose.staging.yml --env-file .env.<env> up -d --build`
   — container `api` menjalankan `migrate` saat start; `worker` menunggu `api` sehat.
4. `infra/deploy/smoke.sh` (tanpa `INSECURE` di staging/produksi publik):
   health, header keamanan, HTTP→HTTPS, host asing ditolak, CORS, cookie
   Secure, login page, host admin → /platform, endpoint terlindungi.
5. Login uji (akun staging), alur singkat: booking → DP → laporan.

## Rollback

- **Kode tanpa migrasi baru**: deploy ulang image/commit sebelumnya.
- **Dengan migrasi**: migrasi Umrovia aditif (kolom/tabel baru, data
  migration hanya menambah grant). Rollback kode lama aman terhadap skema
  baru; jangan menjalankan migrasi mundur di produksi kecuali disetujui —
  CI hanya melatih mundur 1 langkah. Bila skema harus dibalik: restore dari
  backup pra-deploy (BACKUP_RESTORE.md).
- Setelah rollback: smoke test + `verify_integrity`.

## Rollout HSTS bertahap

`SECURE_HSTS_SECONDS=0` saat awal (peringatan `security.W004` disengaja).
Setelah HTTPS stabil di semua host: 300 → 86400 → 31536000 (1 tahun) dalam
beberapa minggu; preload hanya setelah keputusan tertulis.

Header dikirim Caddy untuk **semua** host (`umrovia.com`, `www`, `app.`, `admin.`, `api.`)
dengan `includeSubDomains` dan tanpa `preload`; nilai Django di API ditimpa agar seragam.
Preload tidak ikut menyala saat `SECURE_HSTS_SECONDS` dinaikkan; mengaktifkannya butuh
keputusan tertulis lalu perubahan sengaja di blok `security_headers` Caddyfile.

Naik satu tahap (VPS) — salin cadangan env, ubah nilai, buat ulang `api` + `proxy`:

```bash
cd /srv/umrovia
sudo cp .env.production /etc/umrovia/env.production.bak-$(date +%Y%m%d%H%M%S)
sed -i 's/^SECURE_HSTS_SECONDS=.*/SECURE_HSTS_SECONDS=86400/' .env.production
docker compose up -d api proxy
SITE_HOST=umrovia.com APP_HOST=app.umrovia.com ADMIN_HOST=admin.umrovia.com API_HOST=api.umrovia.com \
  PORT=443 HTTP_PORT=80 infra/deploy/smoke.sh
curl -sI https://umrovia.com/ | grep -i strict-transport
```

Lanjut ke tahap berikut hanya bila selama tahap ini tidak ada keluhan HTTPS/sertifikat
(Uptime Robot hijau, tidak ada host baru tanpa TLS). Mundur: set nilai lebih kecil (atau 0)
dengan langkah yang sama — browser yang sudah menyimpan nilai lama baru lepas setelah
max-age lama habis, jadi tahap 1 tahun praktis tidak bisa dibatalkan cepat.

| Tahap | Nilai | Mulai | Paling cepat ke tahap berikut |
|---|---|---|---|
| 1 | 300 (5 menit) | 2026-10-29 | 2026-11-05 |
| 2 | 86400 (1 hari) | | +14 hari |
| 3 | 31536000 (1 tahun) | | — (preload: keputusan tertulis) |

## Host & DNS

`APP_HOST`, `ADMIN_HOST`, `API_HOST` mengarah ke proxy. Caddy menerbitkan
sertifikat ACME otomatis (`CADDY_TLS=<email>`), menolak Host ≠ SNI (421) dan
host tanpa sertifikat. Kepemilikan domain dan DNS harus diverifikasi sebelum
go-live (Spec §18.6).
