# ADR-0004: Lifecycle Trial — Start, Kuota, Konversi & Expiry

**Status:** Diterima (S04, 22 Okt 2026)
**Konteks:** Roadmap S04 ("Trial lifecycle, demo data, quotas, expiry") +
Spec §5.1, §6.1, §7.1–7.2, §8.2, §8.7, §8.9, POL-07..POL-10, TR01–TR09;
melengkapi ADR-0001/0003.

## 1. Domain & tabel

App baru `modules.trial` dengan tabel kontrol-plane §5.1:
`tenant_trials` (UNIQUE tenant, `dummy_count` atomik, `config_snapshot_json`),
`tenant_trial_events` (append-only — `save`/`delete` eksplisit ditolak model
dan admin), `trial_entitlements` (tenant_id PK), plus `tenants.tenant_environment`
(demo/produksi, UNIQUE (tenant, environment)) di app tenants.

Seperti identitas/tenancy (ADR-0003 §3), tabel trial TIDAK di-RLS-kan:
lifecycle berjalan saat provisioning (sebelum context request) dan di job
expiry tanpa context; proteksi = kolom tenant diisi server-side + otorisasi
endpoint (`trial.read`, `trial.convert`, `trial.demo_booking.create`,
`trial.demo_data.read`).

## 2. Start & state machine (TR01)

`provision_workspace` (verify-email) kini provisioning penuh, satu transaksi:
role Owner (dengan guard kuota user) → environment demo ACTIVE → trial record
(`started_at` = provisioning commit, `ends_at` = +`TRIAL_DAYS`×24 jam, timer
server-side UTC) → state `PENDING_EMAIL → PROVISIONING → TRIAL`. Idempoten;
retry tidak pernah membuat trial/kelompok kedua. Migrasi backfill
`trial/0002` menyelesaikan tenant lama pra-S04 yang masih `PROVISIONING`.

## 3. Kuota (POL-08, TR02–TR04)

- Kuota dummy booking disimpan sebagai **counter** `tenant_trials.dummy_count`
  (bukan derivasi jumlah baris): `SELECT FOR UPDATE` + increment **sebelum**
  create booking demo di dalam transaksi yang sama — create gagal → rollback
  counter (§7.1 langkah 5); **delete record tidak pernah mengembalikan kuota**
  (TR03).
- Limit dibaca dari `config_snapshot_json` (salinan `trial_entitlements` saat
  start — immutable; override admin platform menyusul S16 tanpa mengubah trial
  yang sedang berjalan).
- Guard internal user (`assert_internal_user_quota`, hitungan membership
  ACTIVE nyata — portal user di luar hitungan) dipanggil provisioning dan
  wajib dipanggil alur invite staf S05; error `TRIAL_USER_LIMIT`.
- Booking demo saat ini = record placeholder `DemoBooking` prefix `DEMO-`
  (POL-09) — booking demo nyata berbasis environment menggantikannya di S09;
  semantik counter dipertahankan.

## 4. Konversi & expiry tanpa charge (POL-10, TR08–TR09)

- Satu jalur service `_convert_locked` untuk konversi manual (Owner,
  `confirm: true` eksplisit) dan expiry job — keduanya memegang lock baris
  trial + tenant (`SELECT FOR UPDATE`, §6.1/§7.2 langkah 1).
- Idempoten (TR09): `converted_at` sekali; konversi ulang = no-op, tanpa
  event ganda, tanpa reentry. Hasil: state tenant `ACTIVE`, environment demo
  → `READ_ONLY`, baris environment produksi `ACTIVE` dibuat, event log.
  **Tidak ada pembuatan charge/tagihan apa pun** — wallet/charge hanya setelah
  DP terverifikasi (S13+).
- Expiry: management command `expire_trials` (cron per jam — orkestrasi
  scheduler S17) mengambil kandidat `now >= ends_at`, lalu **re-check status
  di bawah lock** — konversi dini yang commit di antara scan ↔ lock tidak
  dikonversi ganda (race protection teruji urut; lihat test
  `test_expiry_rechecks_under_lock_after_manual_convert`).
- Reminder H-7/H-3/H-1 (§7.1 langkah 6) ditunda ke S16 (modul notifikasi);
  enum event `REMINDER_D*` + dedupe `(trial_id,event_type,recipient)` sudah
  disiapkan.

## 5. Kontrak API & kode error

Endpoint §8.2: `GET /trial/status` (payload §8.7 + `converted_at`),
`POST /trial/convert`, `POST /trial/demo-bookings`, `GET /trial/demo-data`
(read-only setelah konversi). Kegagalan kuota/konversi memakai kode §8.9
dengan HTTP 403: `TRIAL_QUOTA_EXCEEDED`, `TRIAL_USER_LIMIT`,
`TRIAL_ALREADY_USED`; konfirmasi hilang → 400 field error `confirm`.
Matriks RBAC §3: `trial.read` (Owner/Admin), `trial.demo_booking.create`
(Admin/Sales), `trial.convert` & `trial.demo_data.read` (Owner saja).
