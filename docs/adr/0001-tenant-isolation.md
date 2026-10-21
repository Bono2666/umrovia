# ADR-0001: Strategi Isolasi Tenant

**Status:** Diterima (S01, 21 Okt 2026)
**Konteks:** Roadmap S01 T06 + Spec §2.2, §5.6

## Keputusan

Isolasi tenant memakai **tiga lapis (defense-in-depth)**:

1. **PostgreSQL Row Level Security (RLS) — lapis DB (mulai F02/S03).**
   Setiap tabel bisnis berkolom `tenant_id` mendapat `ENABLE/FORCE ROW LEVEL SECURITY`
   dengan policy `tenant_id = current_setting('app.tenant_id', true)::uuid`, termasuk
   `WITH CHECK` (fail-closed bila context kosong / NULL). Environment (demo/production)
   diikat lewat policy + FK komposit (Spec §5.2 integrity note).
2. **Scoped query aplikasi — lapis ORM (sudah ada di S01).**
   `TenantScopedModel` + `TenantScopedManager.get_queryset()` otomatis
   `filter(tenant=current_tenant)` dan **menolak query tanpa context**
   (`TenantContextMissingError`), bukan mengembalikan data kosong.
3. **Authorization per endpoint/objek — lapis API (F02+).**
   Membership + role divalidasi server-side; identitas tenant berasal dari
   host/slug resolver tervalidasi, bukan input client (Spec §2.2).

## Context mechanism

- Per-request: `SET LOCAL app.tenant_id = '<uuid>'` di dalam transaksi, di-set oleh
  middleware setelah membership dikonfirmasi, memakai koneksi request-bound
  (Spec §2.2 — dilarang `SET` global yang bocor ke request lain).
- Background job: context ditandatangani/diambil dari DB oleh service account queue;
  tidak ada bypass RLS untuk akun aplikasi biasa.

## Jalur bypass `without_tenant_guard()`

Hanya untuk: provisioning signup (belum ada context), resolusi membership di
middleware, job background berkonteks bertanda tangan, dan support elevated
(wajib approval + audit + time-limited — Spec §2.2).

## Konsekuensi

- Test wajib membuktikan: (a) tanpa context → ditolak; (b) context tenant A tidak
  membaca/menulis data tenant B di level API **dan** DB; (c) context demo tidak
  bisa membaca record produksi. Test (b) sebagian ada di S01 (ORM layer),
  dilanjutkan dengan test RLS asli di S03 (perlu koneksi Postgres — dijalankan
  di CI/staging).
- `Role` (nullable tenant untuk role sistem) tidak memakai auto-scope; query role
  sistem harus eksplisit.

## Alternatif yang ditolak

- Single-tenant database per travel: isolasi kuat tapi biaya operasi & migrasi
  tidak praktis untuk SaaS pay-per-jamaah.
- `tenant_id` manual di setiap view tanpa RLS: mudah terlewat di query baru
  (risiko kebocoran kritis — lihat Roadmap §8).
