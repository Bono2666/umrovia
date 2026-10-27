# Checklist go-live pilot MVP Umrovia

Rujukan: Product Spec §19.5 (release gates), §13, §17, §18; Roadmap M5.
Disusun 27 Oktober 2026 pada akhir Sprint S19.

**Status: SIAP UNTUK TINJAUAN — belum ditandatangani.** Bukti teknis yang
bisa dibuktikan di repositori sudah lengkap (tabel di bawah). Butir bertanda
**Tindakan** memerlukan infrastruktur, akun pihak ketiga atau keputusan
bisnis/hukum yang tidak dapat diselesaikan dari kode, dan wajib ditutup
sebelum pilot dengan data jamaah sungguhan.

Legenda: ✅ terpenuhi dengan bukti · 🟡 terpenuhi sebagian / di staging lokal ·
⛔ Tindakan (wajib sebelum pilot) · 📝 Keputusan bisnis/hukum.

## 1. Security gate

| Butir | Status | Bukti / catatan |
|---|---|---|
| Otorisasi tenant di server + RLS PostgreSQL (33/33 tabel, membership dikecualikan sesuai ADR-0003) | ✅ | `verify_integrity` (RLS check), `tests/test_rls.py`, matriks UAT SEC01/TR10 |
| MFA staf platform, audit aksi admin, tanpa PII di konsol | ✅ | ADR-0014, `tests/test_platform_console.py` |
| Setting produksi fail-fast; `check --deploy` bersih (kecuali HSTS bertahap) | ✅ | `tests/test_release_security.py`, langkah CI |
| CSRF/CORS/host header; cookie Secure + HttpOnly | ✅ | test rilis + smoke staging 15/15 (lintas host app/admin/api) |
| Log tanpa password/token/PII jamaah | ✅ | `test_logs_never_contain_pilgrim_pii` |
| Audit dependensi (pip-audit, npm audit) dan SAST (bandit via ruff) di CI | ✅ | 14 kerentanan diperbaiki (cryptography 50.0.2, DRF 3.18.3, pytest 9.1.1); npm 0 |
| TLS publik + HSTS bertahap | ⛔ | Caddy siap (`infra/deploy/Caddyfile`); butuh domain & DNS milik sendiri, lalu runbook HSTS |
| Secret produksi di secret manager, terpisah dari staging | ⛔ | `staging.env.example` tanpa secret; pilih secret manager penyedia hosting |
| Pemindai antimalware unggahan dokumen | ⛔ | Mitigasi saat ini: allowlist magic bytes, tolak PDF aktif, unduh sebagai attachment (ADR-0011) |
| MFA untuk role keuangan tenant (Spec §13 "P0 target") | ⛔ | Belum ada; MFA baru untuk staf platform |
| Uji penetrasi pihak ketiga | 📝 | Disarankan sebelum komersial |

## 2. Financial gate

| Butir | Status | Bukti |
|---|---|---|
| Transaksi DB, ledger append-only, idempotency key, row lock | ✅ | PAY01–PAY10, SEC03, `test_ledger_immutable_even_queryset_and_sql` |
| Tidak ada debit sebelum DP terverifikasi | ✅ | PAY03/PAY08, E2E |
| Rekonsiliasi wallet & laporan vs sumber | ✅ | RPT01/RPT02, `reconcile_wallets`, `verify_integrity` harian |
| Midtrans produksi: key produksi, URL notifikasi, uji transaksi kecil | ⛔ | Sandbox teruji (ADR-0010); produksi butuh akun & konfigurasi dashboard Midtrans |
| Rekening penerima top-up platform (manual) | ⛔ | Isi `WALLET_MANUAL_*` produksi |
| Perlakuan pajak/faktur SaaS, minimum top-up, kebijakan refund | 📝 | TBD-01, TBD-02, TBD-04, TBD-05, TBD-10 |

## 3. Trial gate

| Butir | Status | Bukti |
|---|---|---|
| Transaksi demo terpisah dari produksi; watermark DEMO | ✅ | TR05, TR06, TR10 |
| Expiry → aktif tanpa invoice/langganan; konversi tidak mencabut suspend | ✅ | TR08, TR09, `test_trial_conversion_does_not_lift_suspension` |
| Retensi data demo pasca-konversi | 📝 | TBD-06 (usul 30 hari) — job belum dibuat |

## 4. Ops gate

| Butir | Status | Bukti |
|---|---|---|
| Migrasi + rehearsal rollback di CI | ✅ | `.github/workflows/ci.yml` |
| Backup terenkripsi + drill restore | ✅ | `infra/backup/*`; drill: checksum OK, integritas OK, 7.812 baris sama persis, 10 dtk |
| Backup terjadwal harian + salinan offsite | ⛔ | Pasang cron/timer di server + bucket privat region lain (BACKUP_RESTORE.md) |
| Worker latar (antrean, trial, pending charge, integritas harian) | ✅ | service `worker`, heartbeat di `/health` |
| Health/readiness untuk monitoring | ✅ | `/api/v1/health/` (database, cache, worker, email_queue) |
| Alerting & dasbor monitoring | ⛔ | Ambang di MONITORING_INCIDENT.md; pasang uptime check + agregasi log (mis. penyedia hosting/APM) |
| Runbook insiden, backup/restore, deploy/rollback, playbook keuangan & tenant | ✅ | `docs/runbooks/` |
| Pipeline staging | 🟡 | `docker-compose.staging.yml` + smoke 15/15 dan login lintas host di staging lokal; staging publik belum ada |
| Status CI GitHub Actions hijau pada `main` | ⛔ | Verifikasi di GitHub (CLI `gh` tidak tersedia saat S19) |
| Penyimpanan media di bucket objek privat | ⛔ | Saat ini volume Docker; `STORAGES["default"]` dapat diganti S3 privat tanpa ubah kode (ADR-0011) |
| Email transaksional produksi (SPF/DKIM/DMARC, penyedia transaksional) | ⛔ | Gmail SMTP hanya untuk uji; TBD-11 |
| Kapasitas: p95 baca < 500 ms | ✅ | Uji beban 10 pengguna paralel: p95 328 ms, 0 galat; perebutan kursi 1/20 |

## 5. Product gate

| Butir | Status | Bukti |
|---|---|---|
| Alur signup → trial → aktif → booking → DP → debit Rp50.000 → kuitansi/laporan | ✅ | `tests/test_e2e_mvp.py` |
| UAT manual oleh calon travel pilot (kolom "Uji manual") | ⛔ | [MVP_UAT_MATRIX](../uat/MVP_UAT_MATRIX.md) — perlu pelaksana & tanda tangan |
| Konten publik (harga, syarat trial, privasi, ketentuan) ditinjau | 📝 | Halaman ada; tinjauan hukum belum |

## 6. Documentation gate

| Butir | Status | Bukti |
|---|---|---|
| ADR 0001–0014, catatan verifikasi per sprint, matriks UAT | ✅ | `docs/adr`, `docs/development`, `docs/uat` |
| Runbook operasional | ✅ | `docs/runbooks` |
| OpenAPI lengkap dengan skema respons & error | 🟡 | `/api/v1/schema/` tersedia; 47 view tanpa serializer eksplisit tampil generik (peringatan `drf_spectacular.W002`) |
| ERD | 🟡 | Dapat dibangkitkan dari model; belum dilampirkan |

## 7. Hukum & privasi (UU PDP)

| Butir | Status |
|---|---|
| Peran pengendali (travel) / pemroses (Umrovia), DPA dengan travel | 📝 |
| Kebijakan privasi & ketentuan layanan ditinjau penasihat hukum | 📝 |
| Region hosting, retensi, transfer data (TBD-12) | 📝 |
| Prosedur notifikasi insiden data pribadi | 🟡 runbook ada; perlu kontak & SLA resmi |

## Penandatanganan

| Peran | Nama | Keputusan | Tanggal |
|---|---|---|---|
| Product owner | | | |
| Tech lead | | | |
| Keamanan | | | |
| Keuangan / legal | | | |

Pilot dengan data jamaah sungguhan dimulai hanya setelah seluruh butir ⛔
ditutup atau diterima risikonya secara tertulis di tabel ini.
