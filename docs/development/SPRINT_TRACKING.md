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
| T07 | Auth bootstrap (register/verify/login) minimal UI | T07 Auth bootstrap | TODO | dialihkan penuh ke S02 (F02); endpoint & UI signup → S02 |
| T08 | GitHub Actions lint/test + Next.js app shell | T08 Frontend skeleton | DONE | `.github/workflows/ci.yml`; `apps/dashboard` (app shell, design tokens, halaman auth placeholder) |
| T09 | `.env.example`, secret exclusion | — | DONE | `.env.example`; `.gitignore` (`.env`, media, staticfiles) |
| T10 | ADR tenant isolation + structured logging/request-ID | T10 Observability | DONE | `docs/adr/0001-tenant-isolation.md`; `common/{logging,middleware}.py`; test request-ID |

**Exit gate F01:** aplikasi+API bootstrapped lokal ✓ · CI lint/test ✓ (workflow; dijalankan di GitHub) ·
migrasi baseline berhasil ✓ · `pytest` 16/16 ✓ · `ruff` clean ✓

## Sprint berikutnya

| Sprint | Minggu | Fokus | Status |
|---|---:|---|---|
| S02 | 2 | Identity: signup, email verification, login/logout/reset, membership | TODO |
| S03 | 3 | Tenant resolver, RBAC, RLS PostgreSQL, security tests (M1) | TODO |
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
