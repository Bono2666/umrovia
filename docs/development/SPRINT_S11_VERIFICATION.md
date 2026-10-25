# Verifikasi Sprint S11

Tanggal: 26 Oktober 2026. Status: **DONE** untuk exit gate dasar S11.
Branch integrasi S11–S12: `sprint/s12-prepaid-wallet`.
Keputusan: [ADR-0007](../adr/0007-travel-payments-room-pricing.md).

## Cakupan

- Harga Quad/Triple/Double/Single per jamaah, edit tarif, pilihan per peserta
  booking, total gabungan, dan snapshot harga yang tetap.
- Invoice bernomor, rincian peserta, nama penanggung jawab, jatuh tempo,
  saldo tagihan, PDF immutable dan checksum.
- Pencatatan/alokasi pembayaran, draf bukti, pengajuan, verifikasi,
  penolakan, reversal dengan alasan, kuitansi tunggal dan PDF.
- Target minimum DP opsional. Setiap alokasi VERIFIED > Rp0 memenuhi syarat;
  nominal di bawah target tetap dicatat dan diverifikasi.
- RBAC, maker-checker, Sales membaca pembayaran sendiri, tenant/RLS,
  environment, idempotency, event outbox dan konfirmasi produksi tertunda
  sampai charge S12/S13.

## Bukti pengujian

- Suite backend lengkap: **253/253 lulus, 0 gagal, 0 error, 0 skipped**,
  termasuk 39 test baru S11 (16 pembayaran/harga, 19 keamanan/koreksi, 4
  konkurensi). PostgreSQL 18.4 lokal menggunakan database test tersendiri.
  Pemeriksaan khusus penanggung jawab invoice terakhir juga lulus pada DB
  terpisah setelah kode final dilengkapi.
- Ruff, lint frontend, TypeScript dan `git diff --check` lulus.
- Race 10 verifikasi dengan key sama dan berbeda menghasilkan satu kuitansi,
  satu event verifikasi dan satu pengurangan saldo invoice.
- Lima penerbit invoice serentak menghasilkan satu dokumen; dua pencatatan
  yang total alokasinya berlebih menghasilkan tepat satu sukses.
- RLS diuji dengan role PostgreSQL non-superuser: konteks kosong dan tenant
  lain tidak membaca invoice; tenant yang benar membaca invoice miliknya.
- Migrasi dari nol, rollback skema pembayaran dan reapply lulus;
  `makemigrations --check --dry-run` tidak mendeteksi perubahan.
- OpenAPI dibuat dengan anotasi endpoint pembayaran, invoice, booking dan
  harga kamar. Endpoint lama di modul lain masih memiliki graceful-fallback
  schema yang telah ada sebelum S11; ini bukan klaim schema seluruh proyek
  bebas peringatan.

## Browser dan PDF

Chrome menggunakan API Django nyata pada database sementara:

1. Login sebagai operator contoh, membuat paket dengan Quad Rp28.500.000,
   Triple Rp29.500.000 dan Double Rp31.500.000.
2. Mendaftarkan tiga jamaah, membuat keberangkatan dan booking dengan kamar
   campuran, serta reservasi kursi. Total **Rp89.500.000**.
3. Menerbitkan dan mengunduh invoice PDF.
4. Mencatat dan memverifikasi DP **Rp1.000.000** di bawah target opsional
   **Rp5.000.000**, dialokasikan ke satu peserta. Hanya peserta itu eligible.
5. Mengunduh kuitansi PDF dan memeriksa tampilan dark mode serta mobile.
6. Mengedit tarif Quad melalui UI; total dan checksum invoice lama tetap.

Tidak ada runtime error browser. PDF invoice dan kuitansi dirender ke PNG
dan diperiksa visual: label tanggal Indonesia/zona tenant, nilai rupiah,
baris tipe kamar, identitas issuer travel, watermark DEMO dan footer tampil.
Database UI sementara beserta akun dan data contoh telah dihapus.

Artefak lokal sesi (data contoh, tidak dimasukkan ke repository):

- `/private/tmp/umrovia-s11-final.xml`
- `/private/tmp/umrovia-s11-payments-final.xml`
- `/private/tmp/umrovia-s11-openapi.yml`
- `/private/tmp/umrovia-s11-e2e.mjs`
- `/private/tmp/umrovia-s11-edit-check.mjs`
- `/private/tmp/umrovia-s11-production-smoke.mjs`
- `/private/tmp/umrovia-s11-invoice.pdf`
- `/private/tmp/umrovia-s11-receipt.pdf`

## Penerapan lokal

API dan web dibangun ulang dengan konfigurasi development `DEBUG=True`;
Next.js production build dan TypeScript lulus, 24 route termasuk
`/dashboard/invoice` dan `/dashboard/pembayaran` tersedia.

- API, PostgreSQL dan Redis healthy; kedua halaman baru merespons 200.
- Seluruh migrasi terpasang, termasuk `catalog/0002`, `payments/0001`, dan
  `tenants/0006`; tidak ada rencana migrasi tersisa.
- **19/19 tabel bisnis** S07–S11 mempunyai RLS ENABLE+FORCE pada runtime.
- Role yang masih identik dengan default S10 sudah ditingkatkan; jumlah
  default lama yang belum ditingkatkan adalah 0. Role kustom tidak ditimpa.
- Hash file layanan, model, serializer dan PDF pada API berjalan cocok
  dengan source workspace terakhir. Field penanggung jawab invoice ada
  pada runtime.
- Akses anonim `/api/v1/invoices` dan `/api/v1/payments` ditolak 403;
  preflight CORS mengizinkan header idempotency untuk UI.
- Pemeriksaan Chrome terhadap build Docker dengan fixture terisolasi
  memverifikasi field penanggung jawab/payload invoice, dark mode, dan
  mobile tanpa runtime error. Ini melengkapi E2E API nyata yang telah
  dijalankan pada database sementara.
- Database dan volume aplikasi dipertahankan. Tidak ada data contoh
  finansial dari pengujian yang dimasukkan ke database aplikasi.

Selesainya S11 mencakup invoice/receipt serta payment state machine. Wallet
dan debit otomatis tetap S12–S13; produksi mencatat DP VERIFIED dan kuitansi
tanpa mengklaim SaaS charge sudah terjadi. Gateway, scan/unggah bukti,
credit note dan pajak/diskon otomatis belum termasuk tahap ini.
