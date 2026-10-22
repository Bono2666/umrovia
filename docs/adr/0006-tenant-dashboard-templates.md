# ADR-0006: Tenant Dashboard UI & Fondasi Template Dokumen

**Status:** Diterima (S06, 22 Okt 2026)
**Konteks:** Roadmap S06 ("Tenant dashboard, config, template basics" — exit
gate "Tenant admin demo accepted", milestone M2 "trial-ready") + Spec §4.1–4.4
(navigasi/layout/komponen/form), §5.1 (tenant_settings), §5.3 (rekening),
§8.7 (payload trial), §10.2 + baris PDF (template dokumen); melengkapi
ADR-0002 (session auth), ADR-0003 (tenant context/RBAC), ADR-0004 (trial),
ADR-0005 (staff/roles/bank).

## 1. Shell workspace: client-side fetch + guard UI, server otoritas

Seluruh halaman `(workspace)` dibungkus `WorkspaceShell` (client component):
fetch `/me` → tanpa sesi (401/403) → redirect `/login`; tanpa membership
`ACTIVE` → blok "tidak ada workspace aktif". Sidebar mengikuti §4.1 (grup
Ringkasan/Operasional/Keuangan/Dokumen & Laporan/Pengaturan) — menu modul
menyusul dirender non-link bertanda sprint tujuan (S07+, dst.). Header
menampilkan nama workspace + **badge lingkungan teks** DEMO/PRODUCTION
(§4.3: dari `tenant.state` — TRIAL→DEMO, ACTIVE→PRODUCTION), switcher bila
user punya >1 membership `ACTIVE` (`POST /workspaces/switch`).

Keputusan:

- **Tanpa data fetching server-side.** Backend memakai session cookie
  SameSite + CSRF; seluruh data workspace bersifat personal dan dinamis, jadi
  semua fetch terjadi di client (`apiFetch`, `credentials: include`).
  Server components hanya membungkus; konten selalu client-render.
- **Permission klien = UX saja.** Menu/tombol ditutup memakai `permissions`
  dari membership aktif (`hasPermission`, Owner wildcard `*`), TETAPI setiap
  endpoint backend tetap menegakkan `require_permission()` + tenant context
  sendiri. Klien tidak pernah menjadi otoritas (Spec §18.4 anti-trust client).
- **Resolusi workspace aktif di-mirror di klien**: `active_tenant_slug`
  (sesi switch) ?? membership `ACTIVE` pertama — field `active_tenant_slug`
  **aditif** di `GET /me` (S06) agar header tahu workspace sesi tanpa endpoint
  baru; fallback klien identik dengan fallback resolver server (ADR-0003).
- **Banner trial** (`TrialBanner`): countdown absolut ke `ends_at` (tanggal
  id-ID + sisa hari/jam, §4.3) + dipakai/kuota booking dummy & pengguna
  internal (§8.7) + tombol konversi Owner-only (`trial.convert`) dengan
  konfirmasi eksplisit; otomatis disembunyikan pada 403 (peran tanpa
  `trial.read`) atau setelah `converted_at` terisi.
- **Halaman config** memakai endpoint S02–S05 yang ada tanpa BFF/endpoint
  agregat baru: Pengguna & Role (memberships/roles), Profil Travel
  (GET/PATCH `/tenant/settings`, tiga bagian JSON textarea dengan validasi
  JSON inline + ukuran ≤16KB, PATCH per-bagian), Kas & Bank (rekening masked,
  nomor write-only, toggle aktif).
- **Komponen dasar §4.2** disatukan di `components/workspace/ui.tsx`:
  LoadingState/EmptyState/ErrorState/StatusBadge (teks, bukan warna saja)/
  FormField (label + error inline di bawah field terkait).

## 2. Fondasi template dokumen ("template basics")

App baru `modules.documents` (Spec §2.1 domain list; model checklist dokumen
menyusul S07) berisi **renderer murni** `render_invoice()` / `render_receipt()`
yang mengubah konteks dict → HTML siap-PDF:

- Field mengikuti §10.2 persis (invoice: issuer legal name/address, no,
  issue/due, buyer, booking, lines, subtotal/tagihan/bayar/sisa; kuitansi:
  receipt no, tanggal verifikasi, nominal, keperluan, invoice terkait,
  kanal diterima, issuer berwenang).
- **Escaping ketat** (`html.escape` semua nilai konteks — anti-XSS pada
  HTML/PDF); konteks wajib yang hilang → `TemplateContextError`.
- Nominal **integer rupiah** diformat `Rp50.000` (§4.4); nilai non-int/negatif
  ditolak.
- **Output demo** (POL-09/TR05): `environment:"demo"` → nomor ber-prefix
  `DEMO-` + watermark jelas "DOKUMEN DEMO — TIDAK BERLAKU SEBAGAI BUKTI
  PEMBAYARAN".
- **Instruksi bayar hanya `account_masked`** — renderer menerima masked saja
  (§5.3; caller S11 wajib mengirim masked, nomor penuh tak pernah masuk
  template).
- `TEMPLATE_VERSION` ("2026-10-1") ditempel di footer tiap dokumen (baris
  PDF: "HTML-to-PDF + versi template" — versi dicatat sejak awal agar
  dokumen terbit terlacak).

Keputusan: **tanpa endpoint preview/PDF di S06** — Spec §8 hanya memuat
`GET /invoices/{id}/pdf` (S11, butuh model invoice + data booking/payment).
Sprint ini hanya mesin template-nya, diuji unit-test dengan konteks sintetis
(`tests/test_document_templates.py`, 8 tes). Integrasi branding
`tenant_settings.branding_json`/`invoice_config_json` → pemanggilan S11.

## 3. Konsekuensi

- Demo tenant-admin end-to-end: register → verifikasi → trial banner
  live → konfigurasi profil/rekening → undang staf → ganti role/revoke —
  semuanya berjalan tanpa biaya/gateway (M2 gate).
- Halaman operasional (paket, booking, manifest, …) menunggu modul backend
  S07–S11; shell dan pola halaman config S06 menjadi template pengembangannya.
- `modules.documents` kini tanpa model — jangan tambah migrasi sampai S07
  (checklist dokumen) memutuskan skemanya.
