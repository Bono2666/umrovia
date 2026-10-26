# Sprint Tracking — Umrovia

Sumber: `docs/DEVELOPMENT_ROADMAP_Umrovia_v1_0.md` §3–§4 (sprint S01–S19) +
`docs/PRODUCT_SPEC_Umrovia_SaaS_v1_2_Development_Plan.md` §19.4.
Status: `TODO / IN_PROGRESS / BLOCKED / IN_REVIEW / DONE`.

## Sprint S01 — Minggu 1 — Fondasi proyek (F01)

**Goal:** Aplikasi dan API bootstrapped lokal; CI lint/test jalan; migrasi baseline berhasil.

| ID (Roadmap) | Task | Spec §19.4 | Status | Bukti |
|---|---|---|---|---|
| T01 | Repo + README + docs baseline + branch rules | T01 Setup repo | DONE | `README.md`, `legacy/` (pemindahan), commit `0ae1e5f` |
| T02 | Lockfile Python/Node + lint/typecheck + pre-commit | T02 Tooling | DONE | `backend/requirements.lock`, `pyproject.toml` (ruff), `.pre-commit-config.yaml`, `apps/dashboard/package-lock.json` |
| T03 | Docker Compose: postgres, redis, api, web + health | T03 Dev containers | DONE | `docker-compose.yml`, `infra/docker/*`; **tervalidasi lokal via Colima**: `docker compose up --build` → api/db/redis healthy, `/api/v1/health/` 200, web `/login` 200 |
| T04 | Django DRF `/api/v1/health/` + settings split + OpenAPI stub | T04 Django API | DONE | smoke live: `{"status":"ok"}` + `/api/v1/schema/` 200 |
| T05 | Custom User + Tenant/Membership/Role, migrasi baseline bersih | T05 DB migrations | DONE | `identity.0001`, `tenants.0001` sukses di PostgreSQL 18 lokal; CI rehearsal migrate+rollback |
| T06 | Tenant middleware/context + scoped query policy + test isolasi | T06 Secure tenant context | DONE (skeleton) | `modules/tenants/{context,middleware,managers}.py`, 6 test tenants lolos; RLS penuh → S03 |
| T07 | Auth bootstrap (register/verify/login) minimal UI | T07 Auth bootstrap | DONE | dialihkan & diselesaikan di S02 — lihat tabel S02 |
| T08 | GitHub Actions lint/test + Next.js app shell | T08 Frontend skeleton | DONE | `.github/workflows/ci.yml`; `apps/dashboard` (app shell, design tokens, halaman auth placeholder) |
| T09 | `.env.example`, secret exclusion | — | DONE | `.env.example`; `.gitignore` (`.env`, media, staticfiles) |
| T10 | ADR tenant isolation + structured logging/request-ID | T10 Observability | DONE | `docs/adr/0001-tenant-isolation.md`; `common/{logging,middleware}.py`; test request-ID |

**Exit gate F01:** aplikasi+API bootstrapped lokal ✓ · CI lint/test ✓ (workflow; dijalankan di GitHub) ·
migrasi baseline berhasil ✓ · `pytest` 16/16 ✓ · `ruff` clean ✓

## Sprint S02 — Minggu 2 — Identity (F02)

**Goal:** signup → verifikasi email → provisioning workspace/owner membership →
login/logout/reset teruji ("Auth flows tested", Roadmap S02; Spec T07, §7.1, §8.1).

| ID | Task | Spec § | Status | Bukti |
|---|---|---|---|---|
| S02-01 | `POST /auth/register` (validasi email/slug/T&C, slug diparking `PENDING_EMAIL`) | §7.1.1, §8.1 | DONE | `modules/identity/views.py::RegisterView`; test register+validasi |
| S02-02 | Token verifikasi email sekali-pakai + TTL 24 jam (SHA-256 di DB) + email kirim | §7.1.2, T07 | DONE | model `AuthToken` (migrasi `identity.0002`), `services.py`; test invalid/kedaluwarsa/terpakai |
| S02-03 | `POST /auth/verify-email` → user ACTIVE + **provision workspace** (Owner role + membership, state `PROVISIONING`) | §7.1.3 | DONE | `tenants/services.py::provision_workspace` (idempoten); test provisioning+idempoten |
| S02-04 | `POST /auth/resend-verification` — respons generik anti-enumeration | §7.1 | DONE | test resend membatalkan token lama |
| S02-05 | `POST /auth/login` (session cookie, throttle 10/menit, tolak belum verifikasi) + `POST /auth/logout` (CSRF via `GET /auth/csrf`) | §8.1, §7.1.1 | DONE | test login/me/logout flow + test throttle 429 |
| S02-06 | `GET /me` — identitas + daftar membership/workspaces | §8.1 | DONE | `services.user_payload`; test pada flow login |
| S02-07 | `POST /auth/password/forgot` + `/reset` (token 60 menit, sekali pakai, respons generik) | §7.1, §8.1 | DONE | test forgot→reset→login password baru; ADR-0002 |
| S02-08 | UI minimal: form login/register live, halaman `verify-email`, `forgot-password`, `reset-password`, tombol keluar | T07 | DONE | `apps/dashboard/app/{login,register,verify-email,forgot-password,reset-password}`, `components/LogoutButton` |

**Exit gate S02:** `pytest` 35/35 ✓ · `ruff` clean ✓ · `npm run lint` + `npm run build` ✓ ·
smoke live (register → verify → login → /me → logout) ✓ · ADR-0002 ✓

**Catatan/tundaan:** captcha signup & pencegahan abuse (belum ada provider — TBD Spec §16);
force-logout semua sesi lama saat ganti password (harden S19); state tenant → `TRIAL`
menunggu record trial (S04/F03).

## Sprint S03 — Minggu 3 — Tenant resolver, RBAC, RLS (F02 → M1)

**Goal:** "Cross-tenant access denied" — resolver host/sesi, RBAC permission,
RLS PostgreSQL terpasang & teruji (Roadmap S03; Spec §2.2, §3, §5.6, §8.1, §8.9).

| ID | Task | Spec § | Status | Bukti |
|---|---|---|---|---|
| S03-01 | Tenant resolver: subdomain host → sesi switch → fallback; fail-closed tanpa diam-diam fallback | §2.2 | DONE | `modules/tenants/resolver.py`, `middleware.py`; test host subdomain + host-tanpa-keanggotaan → `TENANT_CONTEXT_REQUIRED` |
| S03-02 | Transaksi request + `SET LOCAL app.tenant_id` (koneksi request-bound, auto-reset) | §2.2 | DONE | `TenantContextMiddleware`; test kebocoran `current_setting` setelah request (transactional) |
| S03-03 | `POST /workspaces/switch` (validasi membership server-side, sesi; denial kode sama) | §8.1 | DONE | `tenants/views.py`; test switch sukses/asing/tak-dikenal |
| S03-04 | RBAC: pola `domain.object.action`, matcher wildcard, matriks default role | §3 | DONE | `modules/tenants/rbac.py` (`DEFAULT_ROLE_PERMISSIONS`), ADR-0003 |
| S03-05 | `GET /memberships` digarap `require_permission("memberships.read")` (Owner/Admin) | §8.1 | DONE | test: Owner 200 · Sales 403 `permission_denied` · tanpa context 403 `TENANT_CONTEXT_REQUIRED` · anon 403 |
| S03-06 | Helper RLS `common/rls.py` (pola §5.6 + `NULLIF` fail-closed, identitas tervalidasi) | §5.6 | DONE | `tenant_rls_statements()`; unit test pola & penolakan identifier tak aman |
| S03-07 | Test RLS PostgreSQL: USING lintas-tenant, WITH CHECK, deny tanpa konteks (role non-superuser) | §5.6, §14 | DONE | `tests/test_rls.py` (tabel probe, `SET ROLE`) — 3 test |
| S03-08 | Isolasi API antar-tenant: `/memberships` hanya berisi tenant aktif; `/me` ekspos permissions efektif | §2.2, §8.1 | DONE | `test_tenant_security.py` (12 test) |

**Exit gate S03:** `pytest` 50/50 ✓ · `ruff` clean ✓ · smoke live (switch, subdomain
host, isolasi membership) ✓ · ADR-0003 ✓

**Catatan/tundaan:** tabel bisnis pertama (S05+) WAJIB memanggil `enable_tenant_rls()`
di migrasinya + test probe-nya; pembatasan environment (demo/produksi) diperbarui di
ADR-0004 (tenant_environment ada sejak S04); UI pemilih workspace & menu RBAC → S05;
endpoint tulis `/memberships` & `/tenant/settings` → S05–S06; tabel kontrol-plane
(users/tenants/roles/memberships) sengaja tidak di-RLS-kan (lihat ADR-0003 §3).

## Sprint S04 — Minggu 4 — Trial lifecycle, kuota & expiry (F03)

**Goal:** "Trial → active without auto-charge" — start saat provisioning, kuota
atomik, konversi/expiry tanpa charge (Roadmap S04; Spec §5.1, §6.1, §7.1–7.2,
§8.2/§8.7; POL-07..10; TR01–TR09).

| ID | Task | Spec § | Status | Bukti |
|---|---|---|---|---|
| S04-01 | App `modules/trial`: model tenant_trials / trial_events (append-only) / trial_entitlements / DemoBooking (`DEMO-`) | §5.1 | DONE | `modules/trial/models.py`; test append-only event |
| S04-02 | `tenant_environment` (demo/produksi, UNIQUE per tenant) | §5.1, §2.2 | DONE | `tenants/models.py` + migrasi `tenants/0002` |
| S04-03 | Provisioning penuh: Owner (guard kuota) + demo env + trial start → TRIAL; backfill migrasi tenant lama | §7.1.3, TR01, §6.1 | DONE | `provision_workspace`, `trial/migrations/0002`; test TR01 30×24 jam + idempoten |
| S04-04 | Kuota atomik booking demo: lock+increment sebelum create, rollback saat create gagal, delete tak refund (20) | §7.1.5, POL-08, TR02/TR03 | DONE | `create_demo_booking`; test 20 OK / ke-21 `TRIAL_QUOTA_EXCEEDED`, rollback, no-refund |
| S04-05 | Guard kuota internal user (3; portal di luar hitungan) | POL-08, TR04 | DONE | `assert_internal_user_quota`; test user ke-4 `TRIAL_USER_LIMIT`; S05 wajib memanggil saat invite staf |
| S04-06 | `GET /trial/status` (payload §8.7), `POST /trial/convert` (confirm eksplisit, idempoten), `POST /trial/demo-bookings`, `GET /trial/demo-data` (read-only pasca-konversi) | §8.2, §8.7 | DONE | `trial/views.py`; test payload, RBAC Owner/Admin/Sales, `TRIAL_ALREADY_USED` |
| S04-07 | Konversi dini: lock trial+tenant, demo → READ_ONLY, namespace produksi ACTIVE, ACTIVE + event; TANPA charge | §7.2, POL-10, TR09 | DONE | `convert_trial`; test konversi tunggal/idempoten, `trial_price_idr:0`, 1 event |
| S04-08 | Job expiry `expire_trials`: `now>=ends_at`, re-check di bawah lock (race vs konversi dini), idempoten, no bill | §6.1, TR08 | DONE | management command + `expire_due_trials`; test auto-ACTIVE, re-run 0, race re-check |

**Exit gate S04:** `pytest` 66/66 ✓ · `ruff` clean ✓ · smoke live (register → trial
status → demo booking → convert → ACTIVE) ✓ · ADR-0004 ✓

**Catatan/tundaan:** reminder H-7/H-3/H-1 + notifikasi `trial.*` → S16 (enum event +
dedupe key siap); `GET /platform/trials` & `POST /platform/trials/{id}/extend` → S16
console; guard "trial tenant → write produksi ditolak" penuh menunggu tabel bisnis
berkolom `environment` (S07+); booking demo placeholder `DemoBooking` digantikan
booking nyata S09 (semantik counter dipertahankan); UI trial banner/countdown → S06;
invite staf S05 WAJIB memanggil `assert_internal_user_quota`.

## Sprint S05 — Minggu 5 — Travel profile, staff, roles, bank accounts (F04)

**Goal:** "RBAC and audit passes" — undangan staf, CRUD role berproteksi,
settings travel, rekening bank masked, audit append-only (Roadmap S05;
Spec §3, §5.1, §5.3, §5.5, §8.1, §13).

| ID | Task | Spec § | Status | Bukti |
|---|---|---|---|---|
| S05-01 | App `modules.audit`: `audit_events` append-only (save/update ditolak), `log_event` + `redact()` (sensitif → `***`), gagal audit ≠ gagal operasi | §5.5, §13 | DONE | `modules/audit/{models,services}.py`; test append-only, redact, failure-tolerant |
| S05-02 | App `modules.travel_finance`: `travel_bank_accounts` + **RLS sejak migrasi pertama** (pol §5.6 + NULLIF, SQL beku, FORCE); UNIQUE (tenant, bank, masked) | §5.3, §5.6 | DONE | `travel_finance/0001` + RunSQL; test `pg_policies`/`relforcerowsecurity` |
| S05-03 | `tenant_settings` (`tenant_id` PK: branding/invoice/rules) + backfill `tenants/0004` (role default, Owner `is_system`, settings) | §5.1 | DONE | `tenants/models.py`, migrasi `0003`/`0004`; test provisioning membuat semua role default |
| S05-04 | `GET/PATCH /tenant/settings` (Owner/Admin; per-method `tenant.settings.read/.write`; replace per-bagian, ≤16 KiB) | §8.1, §5.1 | DONE | `test_staff_admin.py`: Owner/Admin 200 · Sales 403 · payload invalid 400 |
| S05-05 | `POST /memberships` invite: user baru → `PENDING_VERIFICATION` + `INVITED` (aktif saat verifikasi email), user ACTIVE → `ACTIVE`; guard kuota trial TR04 | §8.1 | DONE | hook `VerifyEmailView` (`memberships.activated`); test invite/duplikat/role asing 400 · Sales 403 · quota |
| S05-06 | `PATCH/DELETE /memberships/{id}` (Owner-only, `memberships.manage`), revoke soft idempoten, **guard Owner terakhir**, IDOR 404 | §8.1 | DONE | test: ganti role OK · Admin 403 · Owner-terakhir 400 · akses hilang seketika · cross-tenant 404 |
| S05-07 | Roles CRUD (`roles.read/.write`): proteksi `is_system` (Owner), nama "Owner" & grant `*` ditolak, pola §3 tervalidasi, role terpakai tak bisa dihapus, nama unik | §5.1, §3 | DONE | test parametrik validasi · system immutable · in-use 400 · Sales 403 · cross-tenant 404 |
| S05-08 | Rekening bank `GET/POST /bank-accounts`, `PATCH /{id}` (Finance/Owner): `account_number` write-only → `account_masked` 4 digit; nomor asli tak tersimpan/dikirim/diaudit | §5.3, §3 | DONE | test masking (`*********0123`), audit masked, Admin/Sales 403, duplikat 400, cross-tenant 404 |
| S05-09 | Audit event: `memberships.*`, `roles.*`, `tenant.settings.updated`, `bank_accounts.*`, `workspaces.switched`, `trial.converted` (choke-point `_convert_locked`) | §5.5 | DONE | asersi per aksi di `test_staff_admin.py` |
| S05-10 | Matriks RBAC baru: `tenant.settings.read`, `roles.read/write`, `memberships.manage`, `bank_accounts.read/write` (Admin += settings.read+roles; Finance += bank; Admin/Sales − bank) | §3 | DONE | `rbac.py::DEFAULT_ROLE_PERMISSIONS`; test matrix per endpoint |

**Exit gate S05:** `pytest` 105/105 ✓ (39 baru) · `ruff` clean ✓ ·
`makemigrations --check` no-change ✓ · smoke live ✓ · ADR-0005 ✓

**Catatan/tundaan:** email invite + staff UI → S06/S16 (jalur aktivasi
sudah jalan via verifikasi email); baca audit (`GET /audit-events`)/export →
S07+/S16; kas/bank cash-movement & payment gateway → sprint finance/PMT
(launcher TBD); `branch_id` multi-cabang di memberships menyusul F04.

## Sprint S06 — Minggu 6 — Tenant dashboard, config, template basics (F04)

**Goal:** "Tenant admin demo accepted" (M2: trial-ready — workspace usable
tanpa charge) — shell dashboard travel (guard, tenant header + badge
DEMO/PRODUCTION, banner trial countdown, switcher), halaman config
(Pengguna & Role, Profil Travel, Kas & Bank), dan fondasi template
dokumen invoice/kuitansi (Roadmap S06; Spec §4.1–4.4, §5.1, §5.3, §8.7,
§10.2).

| ID | Task | Spec § | Status | Bukti |
|---|---|---|---|---|
| S06-01 | `GET /me` aditif: `active_tenant_slug` (null = fallback membership pertama — klien memakai fallback sama; ADR-0006 §1) | §8.1 | DONE | `MeView`; `test_me_reports_active_tenant_slug` (null → switch → slug) |
| S06-02 | App `modules.documents`: renderer `render_invoice`/`render_receipt` (field §10.2), escape anti-XSS, `TemplateContextError` untuk konteks wajib hilang | §10.2 | DONE | `modules/documents/render.py`; `test_document_templates.py` (injection, field hilang) |
| S06-03 | Format dokumen: nominal integer rupiah `Rp50.000`, nomor demo prefix `DEMO-` + watermark jelas, `TEMPLATE_VERSION` di footer, instruksi bayar hanya `account_masked` | §4.4, POL-09, TR05 | DONE | test format_idr, DEMO/watermark, masked-only |
| S06-04 | `WorkspaceShell`: guard `/me` → /login (401/403), blok tanpa-workspace, sidebar §4.1 lengkap (modul menyusul = non-link bertanda sprint), header nama tenant + **badge teks DEMO/PRODUCTION** (TRIAL→DEMO, ACTIVE→PRODUCTION), switcher bila >1 membership ACTIVE | §4.1, §4.3 | DONE | `components/workspace/WorkspaceShell.tsx`; build lint ✓ |
| S06-05 | `TrialBanner`: countdown absolut ke `ends_at` + used/limit booking & pengguna (§8.7), tombol konversi Owner-only (`trial.convert`) + konfirmasi, auto-hide 403/terkonversi | §4.3, §8.7 | DONE | `components/workspace/TrialBanner.tsx` |
| S06-06 | Halaman Ringkasan live: tile staf/peran/rekening (403 → disembunyikan) + trial card + quick-start | UI-02/UI-03 | DONE | `app/(workspace)/dashboard/page.tsx` |
| S06-07 | Halaman Pengguna & Role: daftar membership, undang staf (invite → verifikasi email), ganti role (PATCH), cabut akses (DELETE), daftar role + permission; tombol berbasis `memberships.write/.manage`, tanpa akses → state khusus | §4.1, §8.1 | DONE | `dashboard/pengguna/page.tsx` |
| S06-08 | Halaman Profil Travel: GET/PATCH `/tenant/settings`, 3 bagian JSON (branding/invoice/rules), validasi JSON inline + ≤16KB, simpan per-bagian, mode baca tanpa `tenant.settings.write` | §4.1, §5.1 | DONE | `dashboard/profil/page.tsx` |
| S06-09 | Halaman Kas & Bank: daftar masked, tambah (nomor write-only), toggle aktif; tanpa `bank_accounts.*` → state tanpa akses | §4.1, §5.3 | DONE | `dashboard/rekening/page.tsx` |
| S06-10 | Komponen dasar §4.2: Loading/Empty/Error state, StatusBadge (teks), FormField + error inline; `lib/format.ts` (rupiah integer, tanggal id-ID) | §4.2, §4.4 | DONE | `components/workspace/ui.tsx`, `lib/format.ts` |

**Exit gate S06:** `pytest` 113/113 ✓ (8 baru: template + `/me`) · `ruff`
clean ✓ · `makemigrations --check` no-change ✓ · `npm run lint` ✓ ·
`npm run build` ✓ (rute /dashboard/{pengguna,profil,rekening}) · smoke live ✓ ·
ADR-0006 ✓

**Catatan/tundaan:** endpoint preview/PDF template → S11 (butuh model
invoice; renderer + `TEMPLATE_VERSION` sudah siap); integrasi branding
`tenant_settings` → pemanggilan S11; notifikasi email invite → S16; modul
operasional (paket/jamaah/booking/manifest) → S07–S10 dengan pola shell +
halaman config S06 sebagai template.

## Sprint S07 — Minggu 7 — Master Jamaah + dokumen secured (F04)

**Goal:** "Jamaah CRUD usable" — master data jamaah per tenant+environment
dengan PII terenkripsi, penanganan duplikat, dan model dokumen ber-versi
(Roadmap S07; Spec §5.2, §5.6, §2.2, §8.3, §10.1; PRD MOD-04).

| ID | Task | Spec § | Status | Bukti |
|---|---|---|---|---|
| S07-01 | App `modules.pilgrims`: `Pilgrim` (kode auto `JM-<8hex>`, UNIQUE(tenant,environment,code), kolom environment S07+) + **RLS sejak migrasi pertama** (pola §5.6 + NULLIF, SQL beku, ENABLE+FORCE) | §5.2, §5.6 | DONE | `pilgrims/0001` + RunSQL; test `pg_policies`/`relforcerowsecurity` (2 tabel) |
| S07-02 | PII: NIK/paspor Fernet-`*_encrypted` di rest, `identity_hash` HMAC tenant-scoped (dedup & pencarian tanpa dekripsi), output API SELALU masked 4 karakter terakhir; key `PII_ENCRYPTION_KEY` (production wajib, local derive dari SECRET_KEY) | §5.2, §10.1 | DONE | `crypto.py`; test enkripsi round-trip, plaintext tak pernah di resp/audit |
| S07-03 | `GET/POST /pilgrims` + `GET/PATCH /pilgrims/{id}`: validasi (NIK 16 digit, email RFC, telepon → +62 E.164, tanggal), pencarian normalisasi aman (nama/kode/telepon/NIK-exact-via-hash), list scoped | §8.3 | DONE | `views.py`, `serializers.py`; test CRUD, validasi, search, scoping |
| S07-04 | Duplikat: identitas sama ditandai `possible_duplicate_of` (MOD-04: ditandai BUKAN digabung otomatis); normalisasi spasi/dash tetap terdeteksi | MOD-04 | DONE | test `test_duplicate_identity_flagged_not_merged` |
| S07-05 | Guard environment server-side: trial → demo; pasca-konversi → production; demo READ_ONLY → write ditolak 403 (tetap terbaca) | §2.2 | DONE | `services.py`; test konversi write-pindah-production |
| S07-06 | `PilgrimDocument`: object_key wajib prefix `tenants/<id>/environments/<env>/pilgrims/<id>/`, versi naik otomatis, UNIQUE(pilgrim,kind,version), review approve/reject **alasan wajib saat reject** (`documents.review`), audit event | §5.2, UI-11 | DONE | test prefix-enforcement, versioning, review reason |
| S07-07 | RBAC `pilgrims.read/.write` (§3): Owner `*`; Admin+Sales tulis; Finance+Operations+DocReviewer baca; cross-tenant IDOR → 404 | §3, §8.3 | DONE | `rbac.py`; test matriks + IDOR |
| S07-08 | Halaman `/dashboard/jamaah`: daftar + pencarian, tambah (NIK/paspor write-only), detail masked + checklist dokumen; sidebar link aktif `pilgrims.read` | §4.1, UI-06 | DONE | `dashboard/jamaah/page.tsx`, `WorkspaceShell.tsx` |

**Exit gate S07:** `pytest` ✓ (11 baru: CRUD/enkripsi/duplikat/search,
matriks RBAC, IDOR, RLS 2 tabel, guard environment, dokumen prefix/version,
review reason) · `ruff` clean ✓ · `makemigrations --check` no-change ✓ ·
`npm run lint` + `tsc --noEmit` ✓ · `npm run build` ✓ (rute
/dashboard/jamaah) · smoke live ✓

**Catatan/tundaan:** Dokumen melekat pada master jamaah (PRD data model),
dan dipakai oleh checklist peserta booking; varian FK per `booking_participant`
belum diimplementasikan. Signed-URL upload/download → S14 (object storage).
Audit 25 Oktober 2026 menutup tindak lanjut formulir wali/mahram, kontak
darurat, kebutuhan khusus dan metadata paspor; detail UI kini mengambil
endpoint detail agar catatan kebutuhan khusus dapat ditampilkan.

## Sprint S08 — Minggu 8 — Paket, keberangkatan & alokasi kursi (F04)

**Goal:** "Paket & departure usable, kursi tak overbooking" — katalog paket
+ jadwal keberangkatan per tenant+environment dengan seat counter atomik dan
gerbang kualitas **capacity concurrency tests** (Roadmap S08; Spec §5.2,
§5.6, §6.5, §8.3, §10.1; PRD MOD-05/MOD-06, BR-002, UAT-01/UAT-02).

| ID | Task | Spec § | Status | Bukti |
|---|---|---|---|---|
| S08-01 | App `modules.catalog`: `TravelPackage` (kode auto `PKT-<8hex>`, UNIQUE(tenant,environment,code), `price_idr` integer rupiah ≤ Rp10 miliar, `inclusions/exclusions_json`, status DRAFT/ACTIVE/INACTIVE/ARCHIVED + `published`) + **RLS sejak migrasi pertama** | §5.2, §5.6, MOD-05 | DONE | `catalog/0001` + RunSQL; test `pg_policies`/`relforcerowsecurity` |
| S08-02 | `GET/POST /packages` + `GET/PATCH /packages/{id}`: validasi (nama, durasi ≤365, harga ≤10M), **publish hanya dari ACTIVE** (guard §5.2/UI-04), list scoped + search `?q/?status`, audit `packages.*` | §8.3, UI-04 | DONE | `catalog/{views,serializers}.py`; test CRUD, publish-guard, scoping, IDOR 404 |
| S08-03 | App `modules.departures`: `Departure` (kode auto `DPR-<8hex>`, package FK PROTECT, CHECK `seats_taken+seats_blocked<=seat_capacity` — BR-002) + `departure_events` **append-only** + **RLS 2 tabel sejak migrasi pertama** | §5.2, §5.6, MOD-06 | DONE | `departures/0001` + RunSQL; test append-only + RLS 2 tabel |
| S08-04 | State machine §6.5: `POST /departures/{id}/transition` DRAFT→OPEN→READY→DEPARTED→COMPLETED atau CANCELED (alasan **wajib**), gerbang OPEN kapasitas ≥1, hook checklist READY (isi riil S10); tiap transisi tulis `departure_events` + audit `departures.transitioned` | §6.5, §8.3, UI-05 | DONE | `services.py::transition_departure`; test happy-path 4 langkah, lompatan ilegal 400, cancel reason, terminal |
| S08-05 | Seat atomik: `reserve_seats/release_seats` = satu UPDATE ber-guard WHERE (baris terkunci → tepat satu pemenang; over-release & count<1 ditolak); `seats_taken` **tidak writable lewat API** (hanya layanan; dipakai booking S09); PATCH `seat_capacity/seats_blocked` ber-guard + CHECK DB pengaman kedua | BR-002, UAT-02, MOD-06 | DONE | `services.py`; test reserve-sampai-penuh, guard PATCH, **race 2-thread kursi terakhir = 1 pemenang (UAT-02)**, **race 10-thread/5-kursi = 5 pemenang** |
| S08-06 | Integritas lintas-environment: departure hanya menunjuk paket environment aktif (ditolak 400, §5.2 integrity note); guard environment pindah ke rumah bersama `modules/tenants/environment.py` (pilgrims re-export) | §5.2, §2.2 | DONE | `tenants/environment.py`; test cross-env 400 + demo READ_ONLY 403 (paket & departure) |
| S08-07 | RBAC baru: `packages.read/.write` (Owner/Admin/Ops tulis; Sales/Finance baca — turunan booking/invoice), `departures.read/.write` (Ops/Admin tulis), transisi via `departures.manage` (Ops/Admin) | §3, §8.3 | DONE | `rbac.py::DEFAULT_ROLE_PERMISSIONS`; test matriks per endpoint + cross-tenant IDOR 404 |
| S08-08 | Halaman `/dashboard/paket` (daftar + tambah + aktifkan/publikasikan/tarik) & `/dashboard/keberangkatan` (gauge kursi, filter status, form + pemilih paket, tombol transisi §6.5, blokir via prompt); sidebar link aktif `packages.read`/`departures.read` | §4.1, UI-04, UI-05 | DONE | `dashboard/{paket,keberangkatan}/page.tsx`, `WorkspaceShell.tsx` |

**Exit gate S08 (capacity concurrency tests):** `pytest` 165/165 ✓ (24 baru:
katalog CRUD/publish/RBAC/RLS, state machine + event append-only, matriks
departures/RBAC/IDOR/guard environment, **2 test konkurensi seat** — 2-thread
kursi terakhir & 10-thread/5-kursi, keduanya tepat-satu/tepat-lima pemenang,
`seats_taken == seat_capacity` tanpa overbooking) · `ruff` clean ✓ ·
`makemigrations --check` no-change ✓ · `tsc --noEmit` + `npm run lint` ✓ ·
`npm run build` ✓ (rute /dashboard/paket & /dashboard/keberangkatan) ·
smoke live ✓

**Catatan/tundaan:** konsumsi kursi atomik oleh booking sudah dipasang S09;
rekonsiliasi berkala `seats_taken` vs daftar booking → S16/S17. Varian harga
per tipe kamar (QUAD/TRIPLE/DOUBLE/SINGLE) telah dipasang S11. Gerbang checklist READY sudah diisi
S10. Audit 25 Oktober 2026 melengkapi pemilih PIC melalui
`GET /departures/staff` (`departures.write`) dan validasi PIC sebagai anggota
tenant aktif dengan akun aktif pada create/PATCH. `FULL`/`CLOSED` MOD-06
diturunkan dari data (available==0 / deadline terlampaui), bukan status
tersimpan — kontrak tersimpan mengikuti §6.5.

## Sprint S09 — Minggu 9 — Booking status & tautan peserta ↔ keberangkatan (F05)

**Goal:** "Booking end-to-end" — pendaftaran jamaah terhubung ke keberangkatan
dengan kursi atomik, state machine booking/peserta, snapshot harga dan kuota
trial (Roadmap S09; Spec §5.2, §6.2, §7.1.5, §8.3, UI-07; PRD MOD-07, UAT-03,
UAT-04, POL-08).

| ID | Task | Spec § | Status | Bukti |
|---|---|---|---|---|
| S09-01 | App `modules.booking`: `Booking` (kode auto `BK-<8hex>`, UNIQUE(tenant,environment,code), status MOD-07), `BookingParticipant` (UNIQUE(booking,pilgrim), `booking_passenger_id` UUID permanen, `participant_status` §6.2, `saas_charge_state` default `not_eligible`, `pricing_snapshot_json`) + `BookingPriceLine` (snapshot §5.2) + **RLS 3 tabel sejak migrasi pertama** | §5.2, §5.6, MOD-07 | DONE | `booking/0001` + RunSQL; test RLS 3 tabel |
| S09-02 | `GET/POST /bookings` + `GET/PATCH /bookings/{id}` (PATCH **hanya DRAFT**: ganti peserta/keberangkatan/catatan dengan guard ulang + delta kuota) + `POST /bookings/{id}/transition`; filter `?status/?departure/?q`, audit `bookings.*` | §8.3, UI-07 | DONE | `booking/{views,serializers}.py`; test CRUD, draft-only PATCH, scoping |
| S09-03 | create booking: departure harus OPEN & belum lewat deadline/berangkat; peserta ≥1 unik & satu environment; **satu jamaah satu booking aktif per keberangkatan (MOD-07)** — divalidasi di bawah `SELECT FOR UPDATE` baris departure + override `allow_duplicate`; snapshot harga 1 baris × n peserta | §5.2, MOD-07, UAT-03/04 | DONE | `services.py::create_booking`; test UAT-03 (3 peserta unik), UAT-04, guard deadline, duplikat+override |
| S09-04 | State machine MOD-07 header + sinkron peserta §6.2: DRAFT→RESERVED (`reserve_seats(n)` atomik — **UAT-02 di level booking**) →CONFIRMED→DOCUMENT_PROCESS→READY_TO_DEPART (hook dokumen S10) →DEPARTED (menunggu keberangkatan berangkat) →COMPLETED; CANCELED alasan wajib + `release_seats`; EXPIRED terkontrol (hanya setelah pendaftaran ditutup) | MOD-07, §6.2, BR-002 | DONE | `services.py::transition_booking`; test rantai penuh, cancel-release, expired-guard, graph §6.2 |
| S09-05 | Kuota trial per booking-jamaah (POL-08, §7.1.5): `dummy_count += n peserta` SEBELUM create dalam transaksi (rollback bila gagal), PATCH mengonsumsi delta, tak pernah dikurangi (TR03) | §7.1.5, POL-08 | DONE | `services.py::_consume_trial_quota`; test 403+rollback, delta PATCH, non-trial lolos |
| S09-06 | RBAC memakai grant `bookings.create` (Owner/Admin/Sales) & `bookings.read` (Ops/DocReviewer baca; Finance tanpa `bookings.*`) sesuai §8.3 Sales/Admin | §3, §8.3 | DONE | test matriks Sales/Ops/Finance + IDOR 404 |
| S09-07 | Halaman `/dashboard/booking` (UI-07): daftar + filter + peserta per baris, form tambah (pilih departure OPEN, pencari jamaah multi-pick, catatan), tombol transisi MOD-07, batalkan ber-alasan, kedaluwarsa; sidebar link aktif `bookings.read`; penanda Leads → P1 (CRM/agen P1, §15) | §4.1, UI-07 | DONE | `dashboard/booking/page.tsx`, `WorkspaceShell.tsx`, tipe `Booking` di `lib/api.ts` |

**Exit gate S09 (Booking end-to-end):** `pytest` 185/185 ✓ (20 baru: create
E2E UAT-03, UAT-04 snapshot vs perubahan harga paket, rantai status MOD-07
penuh dengan sinkronisasi peserta §6.2 + guard tautan keberangkatan, cancel
melepas kursi & expired-guard, **race 2-booking kursi terakhir = 1 pemenang**,
duplikat MOD-07 + override, guard keberangkatan tertutup, draft-only PATCH,
kuota trial per-peserta + rollback + delta, graph §6.2, RBAC/IDOR/read-only/
RLS 3 tabel) · `ruff` clean ✓ · `makemigrations --check` no-change ✓ ·
`tsc --noEmit` + `npm run lint` ✓ · `npm run build` ✓ (rute /dashboard/booking) ·
schema spectacular OK (hanya graceful-fallback APIView pre-existing) ✓

**Catatan/tundaan:** agen/`agent_id` & cabang pada booking mengikuti §15 (P1 —
agensi & portal agen). S11 mengisi tahap DP peserta dan gerbang konfirmasi:
produksi menunggu DP eligible serta charge S12/S13; demo dapat dikonfirmasi
tanpa ledger produksi. Kelengkapan dokumen READY_TO_DEPART sudah diisi S10;
varian harga kamar dan invoice dari snapshot booking telah dipasang S11.
Auto-expiry job EXPIRED → S16
(transisi manual terkontrol dulu); rekonsiliasi `seats_taken` vs booking aktif
→ S16/S17 (counter kini diperbarui atomik lewat reservasi/pelepasan);
penanganan massal booking saat keberangkatan CANCELED → tundaan operasional.

## Sprint S10 — Minggu 10 — Manifest base & checklist operasional (F05)

**Goal:** "Basic departure manifests export" — checklist dokumen wajib per
paket menggerakkan gerbang kesiapan (Roadmap S10; Spec §5.2 `document_requirements`
+ `manifest_versions`, §6.5, §7.6, §8.3, UI-11/UI-12; PRD MOD-08, MOD-12,
OPS-02, OPS-03, UAT-14).

| ID | Task | Spec § | Status | Bukti |
|---|---|---|---|---|
| S10-01 | App `modules.manifest`: `DocumentRequirement` (global `package null` / per paket, partial UNIQUE per lingkup, `mandatory` + `deadline_rule before_ready/before_departure`) + `ManifestVersion` (UNIQUE(departure,version_no), `published_by`, `snapshot_object_key`, `checksum`, append-only) + **RLS 2 tabel sejak migrasi pertama** | §5.2, §5.6 | DONE | `manifest/0001` + RunSQL; test RLS 2 tabel |
| S10-02 | Hook S08/S09 terisi riil: `departures.checklist_complete` (gerbang READY dari requirement `before_ready` vs dokumen APPROVED **versi terakhir** tiap peserta booking aktif; tanpa requirement → lulus), `booking.documents_complete` (gerbang READY_TO_DEPART, strict tanpa exception) + gerbang baru `before_departure` pada transisi DEPARTED | §6.5, MOD-08 | DONE | `manifest/services.py`; `departures/services.py`, `booking/services.py` |
| S10-03 | *Approved exception* §6.5 (OPS-02): flag `checklist_exception` pada `POST /departures/{id}/transition` — wajib `reason`, gate dilewati dengan jejak `departure_events.reason` + audit `departures.transitioned` (`checklist_exception: true`); tanpa exception → 400 `field_errors.checklist` | §6.5, OPS-02 | DONE | serializer+view transisi; test ditolak/wajib alasan/teraudit |
| S10-04 | `GET /departures/{id}/manifest` (`manifest.read`): roster **hanya peserta booking aktif departure itu** (UAT-14), field selalu masked (§10.1), filter MOD-12 `?q/?document=complete\|incomplete/?participant_status/?charge_state`, envelope = metadata + rows + versi + checklist efektif + `?checklist_gaps=1` | §8.3, UI-12, MOD-12 | DONE | `manifest/views.py`; test rows/filter/mask/RBAC/IDOR |
| S10-05 | `POST /departures/{id}/manifest/publish` (`manifest.publish`): snapshot JSON roster di storage (`manifests/{tenant}/{env}/{dep}/v{n}.json`) + `ManifestVersion` bernomor urut unik di bawah lock departure + checksum sha256; audit `manifest.published`; read-only env 403 | §7.6, OPS-04 | DONE | `services.py::publish_manifest`; test versi 1→2, file+checksum, unik, audit |
| S10-06 | **Exit gate:** ekspor CSV `GET /departures/{id}/manifest/export` (`manifest.export`): BOM UTF-8, prefiks nama `DEMO-manifest-` (§7.2), filter MOD-12, audit `manifest.exported` (format/pii/rows/filters); `?pii=1` menuntut `manifest.export_pii` → tanpa izin **403 + audit `manifest.export_denied`** (OPS-03), dengan izin → NIK/paspor hasil dekripsi + kebutuhan khusus | §7.6, §3, OPS-03, UAT-14 | DONE | `services.py::export_csv`; test masked/denied+audit/Owner-full |
| S10-07 | CRUD `/document-requirements` (`documents.requirements.manage`): create duplikat per lingkup 400, override per-kind paket menimpa global, PATCH/DELETE, guard environment (tulis 403 saat read-only), audit `document_requirements.*` | §5.2, UI-11, MOD-08 | DONE | `manifest/views.py`; test CRUD+override+RBAC+read-only |
| S10-08 | Matriks RBAC §3: Admin/Ops += `manifest.read/publish/export` + `documents.requirements.manage` (§8.3 Ops/Admin); **`manifest.export_pii` hanya Owner** (Admin/Ops = S → tidak di-grant v1); Sales/Finance tanpa `manifest.*` | §3, §8.3 | DONE | `rbac.py::DEFAULT_ROLE_PERMISSIONS`; test matriks; audit menambah migrasi `tenants/0005` untuk upgrade grant bawaan lama yang masih identik dengan baseline S05/S07/S08, tanpa menimpa role kustom. |
| S10-09 | Halaman `/dashboard/manifest` (UI-11/UI-12): pemilih keberangkatan + filter q/status dokumen, roster dengan badge kelengkapan & identitas masked, banner kekurangan checklist (petunjuk approved exception), tombol publikasi versi + daftar versi (checksum), panel checklist per paket (tambah/hapus, `before_ready`/`before_departure`), ekspor CSV dengan checkbox "Sertakan PII" bila `manifest.export_pii`; sidebar Manifest aktif `manifest.read` (penanda S10 dilepas) | §4.1, UI-11, UI-12 | DONE | `dashboard/manifest/page.tsx`, `lib/api.ts` (tipe Manifest*), `WorkspaceShell.tsx` |

**Exit gate S10 (Basic departure manifests export):** `pytest` 203/203 ✓
(18 baru: CRUD checklist + override + duplikat lingkup, gerbang READY
ditolak/lulus + flag `mandatory`, approved exception wajib alasan + audit,
gerbang DEPARTED `before_departure`, gerbang booking READY_TO_DEPART, roster
manifest rows/filter/masking/checklist_gaps, RBAC+IDOR manifest, publish
versi 1→2 + file snapshot + checksum + unik + read-only, CSV masked UAT-14 +
DEMO- prefix, OPS-03 denied+audited, PII Owner, RLS 2 tabel) · `ruff` clean ✓ ·
`makemigrations --check` no-change ✓ · `tsc --noEmit` + `npm run lint` ✓ ·
`npm run build` ✓ (rute /dashboard/manifest) · schema spectacular OK (hanya
graceful-fallback APIView pre-existing) ✓

**Catatan/tundaan:** role kustom tetap memakai grant yang dipilih tenant;
role bawaan lama yang belum dikustomisasi ditingkatkan oleh `tenants/0005`.
PII pada **tampilan**
manifest (bukan ekspor) sengaja tidak dibuka — §10.1 default masked, kebutuhan
buka di layar menyusul bila ada permintaan; ekspor PDF/XLSX + antrean
`POST /exports` (§8.3 job) → sprint export (S17); generator dokumen cetak
MOD-12: invoice/kuitansi PDF tersedia S11; formulir/amplop KBIH/rooming list
menyusul S15/S17. Filter manifest per
penerbangan/grup ketika data dimuat; approval exception via alur multi-step
(disetujui role lain) bila PRD menuntut — kini satu langkah transisi dengan
alasan wajib + audit penuh (cukup untuk OPS-02 v1); dokumen melekat pada
jamaah (S07) — pemindahan FK ke `booking_participant` (§5.2 `pilgrim_documents`)
menyusul bila kontrak per-participant dibutuhkan.

## Audit penyelesaian S07–S10 — 25 Oktober 2026

**Status:** DONE untuk 32 task dan exit gate dasar S07–S10. Bukti dan batas
ruang lingkup: [SPRINT_S07_S10_AUDIT.md](SPRINT_S07_S10_AUDIT.md).

- Backend: **214/214 test lulus**, termasuk 11 regresi audit; Ruff lulus.
- Migrasi dari database kosong, rollback/reapply `tenants/0005`, Django
  system check dan `makemigrations --check --dry-run` lulus.
- Frontend: lint, TypeScript dan pengujian Chrome formulir jamaah/PIC/
  pengecualian checklist lulus. Build serta pemeriksaan container lokal
  dicatat di laporan audit.
- Perbaikan tambahan S10: checklist global terisolasi per environment,
  review dokumen tanpa status menghasilkan 400, guard model snapshot
  append-only, dan volume `api_media` untuk persistensi snapshot Docker.

## Sprint S11 — Invoice/kuitansi, verifikasi DP & harga kamar (F06)

**Status:** DONE — implementasi, pengujian, migrasi dan build/runtime lokal
terverifikasi. Keputusan DP pengguna pada
26 Oktober 2026: setiap alokasi VERIFIED > Rp0 memenuhi syarat; minimum
tersedia sebagai target opsional dan tidak menghalangi pembayaran di bawahnya.

| ID | Task | Status | Bukti |
|---|---|---|---|
| S11-01 | Harga QUAD/TRIPLE/DOUBLE/SINGLE per jamaah, harga standar legacy, edit tarif dan RLS | DONE | `catalog/0002`, UI Paket; validasi harga dan booking campuran |
| S11-02 | Pilihan kamar per peserta, snapshot harga stabil, baris booking dari snapshot | DONE | `booking/{services,serializers}.py`, UI Booking; UAT-04 dan browser edit harga |
| S11-03 | Invoice dan line per peserta, penomoran terkunci, issue idempoten, penanggung jawab dan jatuh tempo | DONE | `payments/models.py`, `issue_invoice`; race 5 penerbit = 1 dokumen |
| S11-04 | PDF invoice/kuitansi atomik dalam DB, checksum, issuer travel, DEMO watermark dan download berizin | DONE | `payments/pdf.py`, PDF views; unduhan browser dan QA visual |
| S11-05 | Record DRAFT/SUBMITTED, bukti/referensi, rekening aktif, alokasi tepat sesuai nominal dan batas tagihan | DONE | `record_payment`, evidence PATCH; validasi dan race over-allocation |
| S11-06 | Verify VERIFIED/REJECTED, eligibility > Rp0, target DP opsional dan maker-checker configurable | DONE | `policy.py`, settings; test Rp1 di bawah target Rp5 juta |
| S11-07 | Satu payment satu receipt; saldo dari VERIFIED allocations; idempotency dan outbox durable | DONE | unique receipt, `PaymentOperation`, `PaymentEvent`; race 10 verifier |
| S11-08 | Reversal beralasan dengan actor berbeda, histori/PDF tetap, saldo dan eligibility diperbarui; unpaid cancel → VOIDED | DONE | `reverse_payment`, cancellation hook; test status perjalanan lama tetap |
| S11-09 | Produksi mencatat DP/receipt sambil menunggu S12/S13; demo simulasi tanpa ledger; konfirmasi tanpa shortcut | DONE | `booking_dp_confirmed`, test demo/production/read-only |
| S11-10 | RBAC, Sales scope pembayaran sendiri, upgrade default tanpa menimpa custom; RLS 9 tabel baru | DONE | `tenants/0006`; IDOR, matriks role, probe PostgreSQL non-superuser |
| S11-11 | UI Invoice/Pembayaran, alokasi per jamaah, target DP, verify/reject/reverse, PDF, sidebar dan quick-start | DONE | `/dashboard/invoice`, `/dashboard/pembayaran`; E2E API nyata pada DB sementara |
| S11-12 | Regresi, migrasi clean/rollback, lint/TypeScript/build, OpenAPI, verifikasi runtime dan catatan sprint | DONE | 253/253 test; [laporan verifikasi](SPRINT_S11_VERIFICATION.md), [ADR-0007](../adr/0007-travel-payments-room-pricing.md) |

**Exit gate S11 (Payment state machine tests):** 253/253 backend test lulus
(39 test baru S11); test penanggung jawab invoice tambahan lulus pada DB
terpisah. Ruff, lint frontend, TypeScript dan build Docker API/web lulus.
Migrasi clean/rollback/reapply lulus. Runtime: seluruh migrasi terpasang,
19 tabel bisnis ber-RLS ENABLE+FORCE, tidak ada default role lama tertinggal,
API healthy, halaman Invoice/Pembayaran HTTP 200 dan endpoint anonim 403.
E2E browser API nyata + QA PDF serta pemeriksaan build produksi lulus.

**Batas tahap:** wallet/top-up/ledger dan primitive debit diselesaikan pada
S12 di bawah. Charge dari event DP, retry dan kompensasi SaaS → S13.
Gateway live masih menunggu provider; unggah/scan bukti nyata dan portal → S14+. Worker PDF/email
→ S16. Pajak/diskon otomatis, credit note dan invoice per peserta belum
diimplementasikan; konfigurasi otomatis nonzero ditolak agar tidak diabaikan.
Tahap ini menyelesaikan payment state machine dasar.

## Sprint S12 — Prepaid wallet, top-up manual & immutable ledger (F06)

**Status:** DONE — implementasi, 290/290 test, browser, migrasi dan
build/runtime Docker lokal terverifikasi.
Keputusan pengguna 26 Oktober 2026: **transfer manual dahulu**.

| ID | Task | Status | Bukti |
|---|---|---|---|
| S12-01 | Wallet IDR unik per tenant, saldo BIGINT nonnegatif dan isolasi demo/produksi | DONE | `wallet/models.py`, `production_tenant`; GET demo tidak membuat wallet |
| S12-02 | Top-up manual, instruksi rekening platform snapshot dan Idempotency-Key | DONE | `create_topup`; 10 request serentak menghasilkan satu top-up |
| S12-03 | Submit bukti/referensi tanpa kredit saldo; nominal/field/status ketat | DONE | `submit_topup`; retry tidak mengganti bukti yang sudah diajukan |
| S12-04 | Review/settlement petugas platform berizin, actor berbeda, nominal cocok dan referensi bank unik | DONE | platform list/settle API; Owner tenant tidak berhak PAID |
| S12-05 | Kredit ledger + saldo/version + top-up PAID + outbox atomik | DONE | rollback saat outbox gagal; 10 settlement serentak = satu kredit |
| S12-06 | Primitive debit internal idempoten, lock wallet dan larangan overdraft | DONE | 5 debit dengan saldo untuk 2 → 2 posted, 3 tidak didebit |
| S12-07 | Ledger append-only di model/SQL, tenant parent guard, top-up immutable dan RLS 6 tabel | DONE | `wallet/0001`, SQL mutation tests dan RLS nyata non-superuser |
| S12-08 | Rekonsiliasi ledger/cache/chain/version/top-up; snapshot immutable, alert dan command harian | DONE | `reconcile_wallets`; mismatch exit nonzero tanpa memperbaiki saldo |
| S12-09 | Expiry CREATED aman, PENDING tetap dapat direview; tenant RESTRICTED tetap dapat top-up | DONE | expiry/late settlement/frozen/restricted tests |
| S12-10 | API saldo, ledger/top-up paginated, filter UTC, CSV aman dan izin Finance default konservatif | DONE | `/wallet/*`, `tenants/0007`, RBAC/CSRF/IDOR/CSV tests |
| S12-11 | UI wallet, top-up/bukti/status, mutasi/CSV, kartu dashboard, dark/mobile | DONE | browser API nyata di DB terpisah; sidebar mobile overlay/rail, tanpa overflow |
| S12-12 | Regresi penuh, migrasi clean/rollback/reapply, OpenAPI, lint/TypeScript/build/runtime dan dokumentasi | DONE | [verifikasi S12](SPRINT_S12_VERIFICATION.md), [ADR-0008](../adr/0008-prepaid-wallet-manual-topups.md) |

**Exit gate:** 290/290 test backend lulus (37 tambahan S12); konkurensi,
rekonsiliasi, financial rollback dan RLS nyata lulus. Lint/TypeScript dan
browser desktop/dark/mobile serta CSV lulus. Migrasi clean/rollback/reapply
lulus; build produksi 25 route, API healthy, migrasi terpasang, 6 tabel wallet
RLS ENABLE+FORCE, source runtime cocok dan smoke browser produksi lulus.

**Batas tahap:** debit dari DP terverifikasi, charge unit/tarif snapshot,
pending-charge FIFO/retry, reversal/kompensasi dan milestone M4 → S13.
Wallet S12 tidak otomatis mengubah konfirmasi peserta. Payment gateway live
belum dihubungkan sesuai pilihan transfer manual. Upload/scan file bukti,
worker umum dan platform console menyeluruh mengikuti sprint berikutnya.
Top-up nyata tetap nonaktif sampai rekening penerima platform dikonfigurasi.

## Pemeliharaan setelah S12 — koreksi data

**Status:** DONE (26 Oktober 2026), branch `feat/data-corrections`.
Alur Ubah/Simpan/Batal dilengkapi pada Jamaah, Paket, Keberangkatan, Booking
draf, Kas & Bank, Pengguna/Role dan Profil Travel. Identitas masked tetap,
snapshot harga/UUID peserta dan riwayat rekening terlindungi; editor mengikuti
izin serta environment aktif. Role custom tidak dapat menambah grant di luar
scope actor. Panduan dan bukti: [Koreksi data](DATA_CORRECTIONS.md).

Verifikasi: **303/303 test backend**, 52 targeted, lint/TypeScript/Ruff,
browser API nyata ketujuh form + readonly/dark/mobile, build Docker,
runtime/API healthy dan smoke browser build produksi lulus. Tidak ada migrasi
database baru. Database QA sudah dibersihkan.

## Sprint S13 — Billing event flow, saldo kurang & refund (F06 → M4)

**Status:** DONE — implementasi, pengujian, migrasi dan browser API nyata
terverifikasi (26 Oktober 2026). Branch `sprint/s13-billing-charges`.

| ID | Task | Status | Bukti |
|---|---|---|---|
| S13-01 | Charge `initial` per booking-jamaah, tarif snapshot `SaaSPriceVersion` STD-2026 Rp50.000, partial unique `uq_saas_charge_once` | DONE | `billing/models.py`, `billing/0001`; PAY06/PAY07 |
| S13-02 | Verifikasi DP produksi → charge + DEBIT ledger + peserta CONFIRMED + outbox dalam satu transaksi; urutan lock wallet → booking | DONE | `charge_verified_booking`, PAY01, PAY02 (10 verifikasi serentak = 1 charge) |
| S13-03 | Saldo kurang: DP VERIFIED + kuitansi, charge PENDING beralasan, `saas_charge_status` di respons 200, tenant RESTRICTED, alert dedupe | DONE | PAY03, test wallet frozen |
| S13-04 | Retry FIFO ketat setelah top-up PAID, refund disetujui, tombol tenant, `retry_pending_charges` dan `reconcile_wallets` | DONE | PAY04, FIFO, PAY10 (5 charge dana 2 = 2 POSTED/3 PENDING), race top-up vs verifikasi tanpa deadlock |
| S13-05 | Reversal DP/pembatalan booking mem-VOID charge PENDING; POSTED tidak direfund otomatis; epoch charge baru | DONE | PAY08, PAY09, test reversal |
| S13-06 | Refund: permintaan Owner (peserta batal) → keputusan platform `billing.approve_adjustment` → satu kredit REFUND | DONE | SEC03 (replay + 5 persetujuan serentak = 1 kredit), pemisahan peran |
| S13-07 | Guard DB: terms immutable, transisi valid, POSTED↔DEBIT, REFUNDED↔APPROVED↔REFUND, parent produksi/verified; RLS 3 tabel | DONE | SQL mutation tests, probe RLS non-superuser |
| S13-08 | Rekonsiliasi: DEBIT ↔ charge, REFUND ↔ adjustment, orphan terdeteksi, jumlah pending | DONE | `charge_checks`, test S12 diperbarui untuk invariant baru |
| S13-09 | API: `/wallet/charges`, retry, refund-request, charge-preview, antrean/keputusan refund platform; ledger `REFUND` | DONE | OpenAPI, test izin/IDOR/demo |
| S13-10 | UI Wallet (charge per jamaah, banner RESTRICTED, proses ulang, refund) dan pratinjau biaya saat verifikasi DP | DONE | Playwright API nyata pada DB terpisah, dark/mobile |
| S13-11 | Regresi, migrasi clean/rollback/reapply, lint/TypeScript, dokumentasi | DONE | [verifikasi S13](SPRINT_S13_VERIFICATION.md), [ADR-0009](../adr/0009-saas-charge-pending-refund.md) |

**Exit gate S13 (Exactly-once charge + ledger consistency) dan M4:** DP
terverifikasi menghasilkan tepat satu debit per booking-jamaah dalam
konkurensi nyata; saldo kurang menghasilkan pending charge tanpa menggagalkan
DP; rekonsiliasi konsisten setelah charge, retry dan refund. M4 tercapai.

**Batas tahap:** waiver charge, tarif bertingkat dan chargeback gateway
menunggu keputusan bisnis; platform console UI refund → S18 (API tersedia);
pengiriman notifikasi outbox billing dan penjadwalan command → S16.

## Sprint S14 — Portal jamaah, autentikasi, profil & unggah dokumen (F07)

**Status:** DONE (26 Oktober 2026), branch `sprint/s14-pilgrim-portal`.
Keputusan desain: [ADR-0011](../adr/0011-pilgrim-portal.md). Bukti:
[verifikasi S14](SPRINT_S14_VERIFICATION.md).

| ID | Task | Status | Bukti |
|---|---|---|---|
| S14-01 | Undangan sekali pakai via email (hash token, TTL 7 hari, ganti/cabut), inspeksi publik tersamar | DONE | `portal/services.py`, test undangan/expired/revoked |
| S14-02 | Terima undangan: akun baru terverifikasi atau login wajib untuk email terdaftar; tanpa membership (TR04) | DONE | `login_required`, redirect shell → `/portal` |
| S14-03 | Grant `PortalAccess` + konteks RLS + filter `pilgrim_id` di setiap endpoint (object-level) | DONE | POR02: akses orang lain/UUID tebakan 404, booking grup tanpa data jamaah lain |
| S14-04 | Ringkasan perjalanan: jadwal, progres peserta, tagihan/terbayar/sisa milik sendiri, kuitansi | DONE | PDF hanya untuk dokumen solo |
| S14-05 | Unggah PDF/JPEG/PNG (magic bytes, maks 10 MB, tolak PDF aktif), penyimpanan privat, versi baru | DONE | test berkas tidak aman, batas ukuran, APPROVED terkunci |
| S14-06 | Signed download ≤10 menit terikat user, cek ulang izin, audit | DONE | SEC02, pencabutan langsung berlaku |
| S14-07 | Riwayat versi + alasan penolakan terlihat jamaah, unggah ulang | DONE | POR01 |
| S14-08 | Koreksi kontak oleh jamaah; identitas tetap via travel | DONE | test profil |
| S14-09 | UI portal (`/portal`, `/portal/undangan`) dan sisi staf: undang/cabut, unggah, lihat berkas, setujui/tolak | DONE | Playwright API nyata, mobile |
| S14-10 | Migrasi RLS, regresi, lint/TypeScript, dokumentasi | DONE | 373/373 backend |

**Exit gate S14 (Object-level permissions):** jamaah hanya dapat membaca dan
menulis data jamaah miliknya; akses lintas jamaah/tenant, PDF grup, dan unduhan
setelah dicabut atau kedaluwarsa ditolak oleh test otomatis.

**Batas tahap:** antimalware scanning, notifikasi portal/email berbasis event
(S16), presign S3 saat object storage produksi dipilih.

## Sprint S15 — Operasional keberangkatan, manifest & ekspor PDF (F07)

**Status:** DONE (26 Oktober 2026), branch `sprint/s15-departure-operations`.
UAT: [S15_OPERATIONAL_UAT.md](S15_OPERATIONAL_UAT.md). Bukti:
[verifikasi S15](SPRINT_S15_VERIFICATION.md).

| ID | Task | Status | Bukti |
|---|---|---|---|
| S15-01 | Status pembayaran per jamaah di manifest (tagihan/terbayar/sisa, kamar, DP) + filter pembayaran & booking | DONE | `payment_by_participant` (2 query), OPS05 |
| S15-02 | Ringkasan kesiapan keberangkatan atas seluruh roster (dokumen, DP, lunas, konfirmasi, kursi, piutang, checklist) | DONE | `readiness`, OPS06 |
| S15-03 | Ekspor manifest PDF (A4 lanskap) dan XLSX (aman formula) di samping CSV, filter sama dengan tampilan | DONE | `?file=csv\|xlsx\|pdf`, OPS04 |
| S15-04 | PDF versi terbit dari snapshot beku + verifikasi checksum (versi, waktu, penerbit) | DONE | `manifest/versions/{n}/pdf` |
| S15-05 | Dokumen cetak MOD-12: formulir pendaftaran, label koper, amplop DL; data pribadi lengkap berizin + audit | DONE | `print/{kind}`, OPS03/OPS07 |
| S15-06 | Watermark DEMO dan prefiks `DEMO-` pada seluruh PDF demo | DONE | TR05 |
| S15-07 | UI Manifest: kartu kesiapan, filter pembayaran, PDF/Excel/CSV, cetak dokumen, unduh PDF versi; tautan "Manifest & cetak" di Keberangkatan | DONE | Playwright |
| S15-08 | Dokumen UAT operasional + test otomatis, regresi, lint/TypeScript | DONE | 384/384 backend |

**Exit gate S15 (Operational UAT):** sembilan skenario UAT operasional
(OPS01–OPS07, UAT-14, TR05) dipetakan ke test otomatis yang lulus dan langkah
uji manual pengguna.

**Batas tahap:** rooming list, visa, tiket, itinerary (P1, MOD-14); antrean
ekspor asinkron `POST /exports` dan notifikasi perubahan jadwal (S16);
laporan operasional siap pakai (S17).

## Sprint S16 — Notifikasi email, retry & template (F07)

**Status:** DONE (26 Oktober 2026), branch `sprint/s16-notifications`.
Keputusan: [ADR-0012](../adr/0012-notification-outbox.md). Bukti:
[verifikasi S16](SPRINT_S16_VERIFICATION.md).

| ID | Task | Status | Bukti |
|---|---|---|---|
| S16-01 | Modul `notifications`: outbox transaksional + log pengiriman (RLS), unique key dedupe per event × penerima × kanal | DONE | `uq_notification_dedupe`, RLS test |
| S16-02 | Event NTF-01: booking berhasil, invoice, pembayaran terverifikasi, lunas, dokumen disetujui/ditolak, perubahan jadwal; alert owner charge tertunda | DONE | hook di service, test per event |
| S16-03 | Antrean platform ID-only, klaim SKIP LOCKED + lease, retry backoff, DLQ (`DEAD`), kirim ulang beraudit | DONE | NTF01, test klaim paralel |
| S16-04 | Hook tidak pernah menggagalkan DP/charge (savepoint); SMTP di luar transaksi | DONE | `test_hook_failure_never_breaks_payment` |
| S16-05 | Template berversi: teks travel, validasi variabel wajib/tak dikenal/subjek satu baris, pratinjau, reset | DONE | NTF-03 |
| S16-06 | Inbox portal jamaah (pesan milik sendiri, tandai dibaca) | DONE | NTF-02 |
| S16-07 | Pengingat trial H-7/H-3/H-1 ke owner, satu pesan logis per hari × penerima | DONE | TR07 |
| S16-08 | Worker `run_worker` (antrean + expiry/pengingat trial + retry pending charge) dan service Docker `worker` | DONE | compose |
| S16-09 | Dashboard Notifikasi: ringkasan status, filter, isi pesan, kirim ulang, editor template | DONE | Playwright |
| S16-10 | Grant `notifications.read/manage` + migrasi role default; regresi | DONE | 397/397 backend |

**Exit gate S16 (Queue/idempotency tests):** dedupe event diproses ulang,
klaim antrean tanpa pengiriman ganda, retry → DLQ → kirim ulang, dan isolasi
tenant lulus otomatis.

**Batas tahap:** WhatsApp/SMS (P1), email HTML, webhook bounce provider,
preferensi pesan non-transaksional; antrean ekspor manifest asinkron pindah ke
backlog (ekspor tetap sinkron).

## Sprint berikutnya

| Sprint | Minggu | Fokus | Status |
|---|---:|---|---|
| S02 | 2 | Identity: signup, email verification, login/logout/reset, membership | DONE |
| S03 | 3 | Tenant resolver, RBAC, RLS PostgreSQL, security tests (M1) | DONE |
| S04 | 4 | Trial lifecycle, kuota, konversi & expiry tanpa charge | DONE |
| S05 | 5 | Travel profile, staf/invite, roles, rekening bank, audit (RBAC) | DONE |
| S06 | 6 | Tenant dashboard UI, config, fondasi template dokumen | DONE |
| S07 | 7 | Master Jamaah + dokumen secured (PII terenkripsi, duplikat, RLS) | DONE |
| S08 | 8 | Paket, keberangkatan & alokasi kursi (capacity concurrency tests) | DONE |
| S09 | 9 | Booking status, linking pilgrims to departures (booking end-to-end) | DONE |
| S10 | 10 | Manifest base & checklist operasional (ekspor manifest dasar) | DONE |
| S11 | 11 | Invoice/kuitansi, verifikasi DP dan varian harga kamar | DONE |
| S12 | 12 | Prepaid wallet, top-up manual dan immutable ledger | DONE |
| S13 | 13 | Billing event flow, saldo kurang, refund (M4) | DONE |
| S14 | 14 | Portal jamaah, autentikasi, profil & unggah dokumen | DONE |
| S15 | 15 | Operasional keberangkatan, manifest & ekspor PDF | DONE |
| S16 | 16 | Notifikasi email, retry & template | DONE |
| S17–S19 | 17–19 | mengikuti Roadmap §3 | TODO |

## Keputusan & catatan S01

- Stack: Django 5.2.18 + DRF 3.16.1 + drf-spectacular 0.28 + PostgreSQL (psycopg3).
- Aplikasi lama dipindah ke `legacy/` (referensi logika bisnis; dihapus setelah F06).
- `TenantScopedManager` fail-closed otomatis; bypass `without_tenant_guard()` hanya
  jalur sah (provisioning, middleware resolution, job berkonteks, support elevated).
- Local dev tanpa Docker: Postgres Homebrew + `runserver` + `npm run dev`.
- **Docker lokal (22 Okt 2026):** pasang Colima + Docker CLI via Homebrew; stack
  `docker compose up --build` terbukti jalan penuh (api healthy + health 200, web 200,
  db/redis healthy). `.dockerignore` ditambahkan; entrypoint api pakai `DATABASE_URL` langsung.
- RLS PostgreSQL dan host/slug resolver dikerjakan di S03 (butuh test koneksi PG di CI).
