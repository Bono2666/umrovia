# Runbook — Monitoring, alert & insiden

## Sinyal yang dipantau

| Sinyal | Sumber | Ambang alert | Tindakan awal |
|---|---|---|---|
| API tidak sehat | `GET /api/v1/health/` (publik, tanpa data) | HTTP 503 atau `checks.database = error` 2× berturut | Cek database/koneksi; lihat bagian "API down" |
| Cache/Redis | `checks.cache` | `error` > 5 menit | Restart Redis; throttle & heartbeat bergantung padanya |
| Worker mati | `checks.worker` | `stale` > 5 menit (heartbeat > 120 dtk) | `docker compose logs worker`; restart worker |
| Antrean email macet | `checks.email_queue` | `backlog` > 15 menit | Cek SMTP; status di Notifikasi → Riwayat |
| Integritas data | log `CommandError: Integritas data gagal` dari job harian `verify_integrity` | Setiap kemunculan | Jangan edit ledger; jalankan `manage.py verify_integrity` dan eskalasi |
| Rekonsiliasi wallet | audit `wallet.reconciliation.mismatch` | Setiap kemunculan | Playbook keuangan §Mismatch |
| Galat server | log `level=ERROR` (`django.request` status 5xx) | > 1% request / 5 menit | Cek `request_id` di log |
| Latensi | p95 baca dari proxy/APM | > 500 ms selama 15 menit | Bandingkan dengan baseline uji beban S19 |
| Keamanan login | audit `platform.mfa.failed`, throttle `auth-login` | > 10 gagal / 10 menit per akun | Kunci akun / reset sesi; cek IP |
| TLS | masa berlaku sertifikat | < 14 hari | Periksa ACME Caddy |

Log berformat JSON terstruktur dengan `request_id`; tidak memuat password,
token, NIK, paspor maupun nama jamaah (diuji `test_logs_never_contain_pilgrim_pii`).

## Tingkat insiden

| Sev | Contoh | Respons |
|---|---|---|
| S1 | Kebocoran data antar-tenant, charge ganda massal, data hilang | Segera, semua tangan; pertimbangkan suspend fitur |
| S2 | API down, pembayaran tidak bisa diverifikasi, worker mati > 1 jam | ≤ 30 menit |
| S3 | Fitur sekunder rusak, email tertunda | Hari kerja yang sama |

## Langkah umum

1. Catat waktu mulai, gejala, `request_id` contoh. Tunjuk satu koordinator.
2. Batasi dampak: suspend tenant terdampak (konsol platform) bila ada risiko
   data; nonaktifkan integrasi bermasalah (kosongkan `MIDTRANS_SERVER_KEY`
   → top-up online tertutup, manual tetap jalan).
3. Pulihkan layanan (restart, rollback image — lihat DEPLOY_ROLLBACK.md).
4. Verifikasi: `infra/deploy/smoke.sh`, `manage.py verify_integrity`,
   `manage.py reconcile_wallets`.
5. Pasca-insiden: kronologi, akar masalah, tindakan pencegahan, test regresi.

## Insiden data pribadi (UU PDP)

Bila data pribadi jamaah atau pengguna mungkin terekspos: amankan bukti
(audit, log), hentikan akses yang bocor, nilai cakupan (tenant, jumlah
subjek, jenis data), libatkan penasihat hukum untuk kewajiban notifikasi
kepada pengendali data (travel) dan subjek data sesuai UU PDP. Jangan
menyalin data pribadi ke tiket/chat selama penanganan.

## API down

1. `curl https://<api>/api/v1/health/` → 503? cek database (`pg_isready`), disk, koneksi.
2. `docker compose ps` / log `api`; migrasi gagal saat start akan menahan
   container (entrypoint menjalankan `migrate`).
3. Bila setelah deploy: rollback image (DEPLOY_ROLLBACK.md).
