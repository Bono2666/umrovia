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

**Catatan/tundaan:** FK dokumen ke `booking_participant` (§5.2 varian) →
S09 saat tabel `booking_participants` ada — pada S07 dokumen melekat pada
jamaah (PRD data model); signed-URL upload/download → S14 (object storage);
wali/mahram & catatan kebutuhan khusus sudah di model/detail payload —
UI form penuh menyusul bersama booking S09.

## Sprint berikutnya

| Sprint | Minggu | Fokus | Status |
|---|---:|---|---|
| S02 | 2 | Identity: signup, email verification, login/logout/reset, membership | DONE |
| S03 | 3 | Tenant resolver, RBAC, RLS PostgreSQL, security tests (M1) | DONE |
| S04 | 4 | Trial lifecycle, kuota, konversi & expiry tanpa charge | DONE |
| S05 | 5 | Travel profile, staf/invite, roles, rekening bank, audit (RBAC) | DONE |
| S06 | 6 | Tenant dashboard UI, config, fondasi template dokumen | DONE |
| S07 | 7 | Master Jamaah + dokumen secured (PII terenkripsi, duplikat, RLS) | DONE |
| S08–S19 | 8–19 | mengikuti Roadmap §3 | TODO |

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
