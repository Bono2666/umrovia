# Runbook — Deploy, staging & rollback

## Lingkungan

| Lingkungan | Cara | Aturan |
|---|---|---|
| Lokal | `docker compose up -d` | Data dummy, gateway sandbox/manual |
| Staging | `docker-compose.staging.yml` + `.env.staging` | Setting produksi, host sendiri, Midtrans **sandbox**, database terpisah |
| Produksi | Sama dengan staging, secret produksi | Persetujuan rilis (GO_LIVE_CHECKLIST), backup sebelum deploy |

## Deploy staging/produksi

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

## Host & DNS

`APP_HOST`, `ADMIN_HOST`, `API_HOST` mengarah ke proxy. Caddy menerbitkan
sertifikat ACME otomatis (`CADDY_TLS=<email>`), menolak Host ≠ SNI (421) dan
host tanpa sertifikat. Kepemilikan domain dan DNS harus diverifikasi sebelum
go-live (Spec §18.6).
