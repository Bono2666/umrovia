# ADR-0003: Konteks Tenant per Request, RLS PostgreSQL & RBAC

**Status:** Diterima (S03, 22 Okt 2026)
**Konteks:** Roadmap S03 ("Tenant resolver, RBAC, RLS, security tests") +
Spec §2.2, §3, §5.6, §8.1, §8.9; melengkapi ADR-0001.

## 1. Resolusi tenant (urutan & sumber kebenaran)

1. **Subdomain host** — `<slug>.umrovia.com` (produksi) / `<slug>.localhost`
   (dev; `ALLOWED_HOSTS` memuat wildcard `.localhost`). Sumber identitas paling
   eksplisit (§2.2: "domain/slug tervalidasi … client-supplied `tenant_id` tidak
   boleh dipercaya" — `?tenant=`/header tidak pernah dibaca).
2. **Sesi hasil `POST /workspaces/switch`** — slug divalidasi terhadap membership
   ACTIVE di server saat switch (§2.2 mengizinkan "workspace di token").
3. **Fallback dev-local** — membership ACTIVE pertama (tanpa subdomain & switch).

**Fail-closed eksplisit:** bila host/sesi menunjuk slug `X` dan user bukan anggota
aktif `X`, context KOSONG (endpoint tenant → `TENANT_CONTEXT_REQUIRED`) — **tidak**
ada fallback diam-diam ke tenant lain, agar tidak pernah terbaca data tenant yang
bukan maksudnya. Penolakan switch memakai kode `TENANT_ACCESS_DENIED` yang sama
untuk slug asing/tak dikenal (tanpa oracle enumerasi).

## 2. Mekanisme `SET LOCAL app.tenant_id`

`TenantContextMiddleware` membungkus **seluruh request** dalam
`transaction.atomic()` dan menjalankan
`SELECT set_config('app.tenant_id', <uuid>, TRUE)` pada koneksi request-bound —
persis §2.2 ("SET LOCAL … setiap transaksi setelah membership dikonfirmasi; jangan
memakai SET global"). Karena `is_local = TRUE`, nilai **otomatis hilang saat
COMMIT/ROLLBACK** transaksi request berakhir → tidak pernah bocor ke request
berikutnya pada koneksi pool (`CONN_MAX_AGE`). Bila koneksi mati di tengah
request, koneksi baru lahir tanpa konteks → RLS gagal-tertutup (diinginkan).

Catatan test: dalam test non-`transactional`, atomic middleware = savepoint
(release tidak membatalkan `SET LOCAL`) — jadi test kebocoran memakai
`@pytest.mark.django_db(transaction=True)` (transaksi nyata, COMMIT penuh).

## 3. RLS: pola, `NULLIF`, dan tabel yang di-RLS-kan

- Pola persis §5.6 (`ENABLE` + `FORCE` + policy `USING`/`WITH CHECK`) dibungkus
  `common/rls.py::tenant_rls_statements()` dan WAJIB dipanggil di migrasi setiap
  **tabel bisnis** (§5.2+) yang baru dibuat — diverifikasi test pada tiap tabel.
- **Deviasi terkontrol:** kondisi memakai
  `NULLIF(current_setting('app.tenant_id', true), '')::uuid`. Tanpa `NULLIF`,
  konteks kosong (`''`) membuat cast `''::uuid` **error** (bukan deny); dengan
  `NULLIF` → `NULL` → perbandingan tidak pernah cocok → 0 baris (fail-closed),
  sesuai catatan §5.6 "requires a fail-closed policy if missing tenant context".
- **Tabel kontrol-plane TIDAK di-RLS-kan** (identity/tenancy §5.1: `users`,
  `tenants`, `roles`, `memberships`, `authtokens`, trial menyusul): resolusi
  membership harus terjadi **sebelum** context ada, dan `/me` sengaja
  mengagregasi membership lintas tenant. Dijaga lapis 2 (scoped manager
  fail-closed) + otorisasi endpoint; `roles`/`memberships` yang dibaca
  `select_related` tetap terlindungi oleh scope aplikasi di semua jalur baca.
- Superuser PostgreSQL selalu bypass RLS (FORCE pun tidak mengefektifkannya) —
  test memindahkan sesi ke role non-superuser (`SET ROLE`) untuk membuktikan
  perilaku; akun aplikasi produksi dikonfigurasi **bukan superuser** (Spec §13).
- Pembatasan **environment** (demo vs produksi, §2.2/§5.6) menunggu kolom
  `environment` pada tabel bisnis → dikerjakan bersama trial (S04) dan tabel
  bisnis pertama (S05+), termasuk test "record produksi tak terbaca dari context
  demo".

## 4. RBAC

- Pola permission `domain.object.action` (§3), grant disimpan di
  `Role.permissions_json` (list; format dict lama `{"perm": true}` tetap
  didukung). Matcher: `*`, `domain.*`, `domain.object.*`, exact.
- Matriks default `DEFAULT_ROLE_PERMISSIONS` mengikuti tabel §3: **hanya Owner**
  (wildcard `*`) yang memegang `payments.verify`, `wallet.topup`, `trial.convert`,
  `reports.export_pii` — baris `S` (butuh approval) diperlakukan **tidak diberi**
  sampai mekanisme approval/scope ada.
- Penegakan: `require_permission("...")` (DRF permission) — tanpa context →
  `TENANT_CONTEXT_REQUIRED`; context ada tapi tanpa grant → 403
  `permission_denied`. Endpoint pertama yang digarap: `GET /memberships`
  (Owner/Admin §8.1); endpoint tulis memberships & `/tenant/settings` → S05–S06.
