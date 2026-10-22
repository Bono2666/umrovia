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
di migrasinya + test probe-nya; pembatasan environment (demo/produksi) menunggu kolom
`environment` (S04+); UI pemilih workspace & menu RBAC → S05; endpoint tulis
`/memberships` & `/tenant/settings` → S05–S06; tabel kontrol-plane (users/tenants/
roles/memberships) sengaja tidak di-RLS-kan (lihat ADR-0003 §3).

## Sprint berikutnya

| Sprint | Minggu | Fokus | Status |
|---|---:|---|---|
| S02 | 2 | Identity: signup, email verification, login/logout/reset, membership | DONE |
| S03 | 3 | Tenant resolver, RBAC, RLS PostgreSQL, security tests (M1) | DONE |
| S04–S19 | 4–19 | mengikuti Roadmap §3 | TODO |

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
