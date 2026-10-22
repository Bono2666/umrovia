# ADR-0005: Staff & RBAC Admin — Invite Model, Rekening Masked, Audit, Guard Owner

**Status:** Diterima (S05, 22 Okt 2026)
**Konteks:** Roadmap S05 ("Travel profile, staff, roles, bank accounts — RBAC
and audit passes") + Spec §3 (matriks), §5.1 (tenant_settings/roles),
§5.3 (travel_bank_accounts), §5.5 (audit_events), §8.1 (endpoint), §13 (Audit);
melengkapi ADR-0003 (context/RLS/RBAC) dan ADR-0004 (trial/kuota).

## 1. Model invite staf (tanpa tabel invite terpisah)

`POST /memberships` (Owner/Admin, `memberships.write`) menerima `{email,
role_id}` dan menempuh dua jalur:

- **User baru** → akun dibuat `PENDING_VERIFICATION` **tanpa password**
  (`set_password(None)` = unusable) + membership `INVITED`. Aktivasi terjadi
  lewat jalur verifikasi email yang sudah ada: `resend-verification` menerbitkan
  token EMAIL_VERIFY → `verify-email` mem-balik `INVITED → ACTIVE` (hook di
  `VerifyEmailView`) + audit `memberships.activated`. Set password dilayani
  reset-password yang sudah ada — **tidak ada tabel/token/kirim-email invite
  baru**.
- **User `ACTIVE` sudah ada** → membership langsung `ACTIVE`.

Alasan: Spec §8.1 hanya mendaftarkan `/memberships` (tanpa endpoint accept
invite); memanfaatkan state machine identitas S02 menghindari paralel token
kind + endpoint baru, sekaligus tetap menjamin "orang di balik email" (verifikasi
email) sebelum akses workspace. Pengiriman email invite → S16 (notifikasi);
kuota trial dipanggil sebelum create (`assert_internal_user_quota` → 403
`TRIAL_USER_LIMIT`, TR04 — dihitung membership `ACTIVE`, jadi undangan yang
belum diterima tidak memakan kuota).

`PATCH/DELETE /memberships/{id}` memakai permission terpisah
**`memberships.manage` — hanya Owner** (Admin punya `memberships.write` untuk
invite/list tapi TIDAK `manage`), persis §8.1 ("PATCH/DELETE: Owner").
Revoke bersifat **soft** (`status=REVOKED`, idempoten; `changed:false` pada
panggilan ulang) agar jejak audit tetap utuh.

## 2. Guard Owner terakhir (anti workspace yatim)

Menurunkan role atau mencabut membership **Owner terakhir yang `ACTIVE`**
ditolak 400 (`field_errors`) — berlaku untuk diri sendiri maupun anggota lain,
di `assign_membership_role` dan `revoke_membership` (dihitung di bawah baris
yang sama, tanpa predikat nama role duplikat). Setelah Owner kedua ada,
guard melonggar. Dampak sampingan yang disengaja: mencabut diri sendiri
menghapus konteks tenant sesi itu seketika (request berikutnya 403) — diuji.

## 3. Role CRUD dengan proteksi sistem

`GET/POST /roles`, `PATCH/DELETE /roles/{id}` (Owner/Admin; `roles.read` /
`roles.write`). Aturan:

- Role **`is_system`** (Owner — ditandai saat provisioning + backfill
  `tenants/0004`): nama & permission tak bisa diubah, tak bisa dihapus.
  Nama "Owner" tidak boleh dipakai role buatan user.
- Permission buatan user tervalidasi pola §3
  (`^[a-z_]+(\.(\*|[a-z_]+))*$`, maks 64): wildcard antar-segmen (`bookings.*`)
  diizinkan; grant tunggal `*` **dilarang** (hanya role Owner sistem).
- Role terpakai membership tidak bisa dihapus (400); nama unik per tenant
  (pre-check + constraint).
- `provision_workspace` kini membuat **semua** role default per matriks §3
  (Owner `is_system` + Admin/Sales/Finance/Operations/Document Reviewer) +
  baris `TenantSettings` — backfill untuk tenant lama.

Permission baru: `tenant.settings.read`, `roles.read`, `roles.write`,
`memberships.manage`, `bank_accounts.read/write` (Finance saja; Admin/Sales
tanpa akses rekening — matriks §3).

## 4. Rekening bank: nomor asli tidak pernah ada

Tabel bisnis pertama `travel_finance_travelbankaccount`
(§5.3: bank_name, account_masked, account_name, active; UNIQUE
(tenant, bank_name, account_masked)) — **memakai RLS sejak migrasi pertama**
(pol §5.6 + `NULLIF` fail-closed, SQL dibekukan di `0001`, FORCE ROW LEVEL
SECURITY; diuji via `pg_policies` + probe test).

Endpoint (`GET/POST /bank-accounts`, `PATCH /bank-accounts/{id}`) hanya
menerima `account_number` (write-only) → disimpan sebagai `account_masked`
(max 4 digit terakhir, `mask_account_number`) dan hanya nilai masked yang
dikembalikan/diaudit. "Ganti nomor" = buat ulang (PATCH tidak menerima nomor).
Guard IDOR: fetch memakai manager scoped → id asing 404.

## 5. Audit append-only ter-redact (Spec §5.5)

App `modules.audit`, tabel `audit_events` (kolom: tenant, actor, action,
object_type/object_id, changes_json, ip, occurred_at; index (tenant,
occurred_at)). Keputusan:

- **Append-only**: `save()` update & `delete()` ditolak model (dan admin
  read-only) — sama polanya dengan `tenant_trial_events`.
- **Tabel kontrol-plane → TIDAK di-RLS-kan** (ADR-0003 §3): log harus bisa
  ditulis dari job tanpa context; proteksi = kolom tenant diisi server-side
  dari context request + otorisasi baca (read endpoint → S07+).
- `log_event()` melewati `changes_json` lewat `redact()`: nilai kunci sensitif
  (password/token/secret/account_number/otp/authorization) di-mask `***` —
  nomor rekening penuh tidak pernah masuk audit/log.
- **Kegagalan menulis audit tidak menjatuhkan operasi utama** (catch + log
  exception; diuji dengan manager yang dibuat gagal).
- Event yang direkam S05+: `memberships.invited/activated/role_changed/revoked`,
  `roles.created/updated/deleted`, `tenant.settings.updated`,
  `bank_accounts.created/updated`, `workspaces.switched`,
  `trial.converted` (satu choke-point di `_convert_locked` — menutup jalur
  manual **dan** expiry job).

## 6. Settings (§5.1) — `GET/PATCH /tenant/settings`

Owner/Admin (`tenant.settings.read` per-GET, `tenant.settings.write` per-PATCH
— `get_permissions()` per method). `tenant_settings` = `tenant_id` PK
(OneToOne) berisi `branding_json`, `invoice_config_json`, `rules_json`;
dibuat saat provisioning + backfill + lazy `get_or_create` di GET. PATCH
mengganti **seluruh bagian yang dikirim** (bukan merge deep — deterministik,
mudah diaudit; bagian tak dikirim tidak berubah), maks 16 KiB per bagian,
wajib objek JSON, patch kosong → 400.

## Konsekuensi / ditunda

- Kirim email invite + tampilan staff UI → S06/S16.
- Baca audit (`GET /audit-events`) + export → S07+/S16.
- Rekening virtual account/payment gateway tetap TBD (§PMT); kas/bank travel
  (cash movement) → sprint finance menyusul.
