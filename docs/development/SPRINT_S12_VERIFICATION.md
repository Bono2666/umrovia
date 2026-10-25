# Verifikasi Sprint S12

Tanggal: 26 Oktober 2026. Status: **DONE** untuk exit gate S12.
Branch integrasi: `sprint/s12-prepaid-wallet`, mencakup perbaikan audit
S07–S10, implementasi S11–S12, dan perbaikan kesejajaran filter wallet.

## Cakupan dan keputusan

Prepaid wallet, top-up manual, immutable ledger, primitive debit atomik dan
rekonsiliasi. Pengguna memilih transfer manual dahulu pada 26 Oktober 2026.
Rincian kebijakan dan API: [ADR-0008](../adr/0008-prepaid-wallet-manual-topups.md).
Dokumen baseline PRD/Product Spec/Roadmap tidak diubah.

## Bukti pengujian

- Suite backend lengkap: **290/290 lulus, 0 gagal/error/skipped**;
  `/private/tmp/umrovia-s12-full.xml`, 251 detik. S12 menambah 37 kasus
  (`test_wallet.py` dan `test_wallet_concurrency.py`) di atas 253 kasus S11.
- Targeted payment security + wallet/concurrency: 53 lulus pada iterasi
  sebelum penambahan kasus restricted/demo/pemisahan DP terakhir.
- Konkurensi PostgreSQL dengan koneksi/thread terpisah: 10 create retry
  satu ID; 10 settlement satu kredit/outbox; 5 debit berbeda dengan dana untuk
  dua hanya mendebit dua, saldo nol; UUID debit sama tetap satu ledger.
- Tidak ada kredit saat create/submit, nominal/ref settlement wajib cocok,
  global bank reference dedup, maker berbeda, penolakan beralasan, rollback
  seluruh settlement saat pembuatan outbox gagal.
- Debit internal terdeduplikasi dan tidak pernah overdraw. Pembayaran DP,
  invoice/kuitansi dan status peserta tidak diubah oleh top-up S12.
- Ledger update/delete lewat model, QuerySet dan SQL ditolak. Nominal top-up,
  bukti submitted dan parent tenant terlindungi di database.
- RLS ENABLE + FORCE pada keenam tabel wallet; probe dengan role PostgreSQL
  non-superuser: context kosong/tenant lain tidak melihat baris, tenant benar
  melihat baris miliknya. Platform context dipulihkan setelah settlement.
- Owner wildcard tidak dapat melakukan settlement platform; is_staff tanpa
  permission tidak cukup; requester tidak dapat settle sendiri. Admin/Sales/
  Ops tidak mendapat wallet default; Finance read/top-up/export, custom
  grants tetap. Anonymous, CSRF, IDOR, akun suspended dan demo diuji.
- Wallet frozen dan tenant suspended tidak menerima mutasi; RESTRICTED
  masih dapat top-up. CREATED expired ditutup oleh command, PENDING tidak
  hilang dan settlement bank terlambat tetap dapat dicatat.
- Rekonsiliasi memeriksa saldo/cache/chain/version dan top-up dengan ledger;
  mismatch membuat snapshot/audit/log + exit nonzero tanpa mengubah saldo.
- CSV mengikuti filter ledger, no-store dan menetralkan formula spreadsheet;
  pagination serta input tanggal/status/unknown fields ditangani.
- Ruff, git diff check, ESLint dan TypeScript lulus.
- Uji tambahan batas tanggal pada implementasi terakhir lulus: tanggal tidak
  canonical, tanggal tidak valid, tanggal maksimum yang menyebabkan overflow,
  dan rentang terbalik mengembalikan 400.

## Browser dan artefak

Runtime Node REPL/in-app browser tidak tersedia; menggunakan Playwright yang
telah terpasang dan Chrome lokal. API Django :8002 dan Next :3001 memakai
database **terpisah** `umrovia_s12_ui` dengan akun/travel/rekening fiktif.
Tidak menulis data keuangan uji ke database aplikasi.

`/private/tmp/umrovia-s12-browser.mjs`: login UI → Wallet → buat instruksi
Rp100.000 → tampil rekening platform → ajukan referensi/lokasi bukti → saldo
tetap → login platform berizin → settlement dua kali → satu kredit → update
UI → unduh CSV → dark/mobile → dashboard summary. Tidak ada pageerror.
Pengulangan QA memakai saldo awal fixture yang sudah ada, sehingga snapshot
terakhir berisi dua settlement uji (Rp200.000), bukan dua kredit satu transfer.

`/private/tmp/umrovia-s12-mobile-check.mjs`: viewport 390px, rail 64px,
konten 326px, tanpa page overflow. Sidebar dibuka, pilih navigasi, lalu
menutup kembali. Screenshot diambil setelah transisi selesai. Pemeriksaan
ini memperbaiki masalah sidebar expanded yang sebelumnya menyempitkan konten.

Artefak lokal: `umrovia-s12-wallet-light.png`, `umrovia-s12-wallet-dark.png`,
`umrovia-s12-mobile-final.png`, `umrovia-s12-ledger.csv` di `/private/tmp`.
Ledger uji juga telah direkonsiliasi lewat command.
Perbaikan lanjutan filter wallet menghilangkan margin vertikal bawaan pada
kolom filter. Pemeriksaan Chrome pada build Docker terakhir memastikan sisi
bawah ketiga field dan tombol Terapkan sejajar; dark mode/mobile lulus.
Lint, TypeScript dan build frontend setelah perbaikan juga lulus.
API/frontend QA telah dihentikan; database UI/schema sementara dibersihkan
setelah pengujian. Artefak di `/private/tmp` tetap tersedia.

## Migrasi, schema dan runtime

Migrasi dari database kosong lulus; rollback `wallet zero` (termasuk dependensi
`tenants/0007`) dan reapply lulus pada database schema sementara. Tidak ada
perubahan model/migrasi yang tertinggal. Model: `wallet/0001`, Finance defaults
`tenants/0007`.
OpenAPI di `/private/tmp/umrovia-s12-openapi.yml`: endpoint wallet/platform,
Idempotency-Key wajib create dan CSV response terverifikasi. APIViews lama
di luar S12 masih menghasilkan warning/error inferensi serializer pada
generator; tidak mengklaim seluruh repository schema bebas warning.

Build Docker API/web lulus, Next menghasilkan 25 route termasuk Wallet,
TypeScript build lulus. API healthy; seluruh migrasi terpasang, 6 tabel wallet
ber-RLS ENABLE+FORCE. Default Finance lama tersisa 0; 13 default Finance
terpasang dengan grant terkini, custom role tetap dipertahankan. Permission
platform `wallet.settle_topup` tersedia. SHA256 12 file source wallet pada
container API cocok dengan source lokal.

HTTP runtime: health API 200; wallet/topups anonim 403; halaman Wallet 200.
DB/Redis healthy dan web berjalan. `manage.py check` serta `migrate --check`
lulus. Bukti: `/private/tmp/umrovia-s12-runtime.log` dan
`umrovia-s12-docker-build.log`.

Smoke browser **build produksi** di localhost:3000 lulus untuk create, submit,
Idempotency-Key, saldo tetap sebelum settlement, dark mode dan mobile tanpa
pageerror/overflow. Seluruh API smoke ini diintersep fixture, sehingga tidak
menulis transaksi ke database aplikasi. Artefak:
`/private/tmp/umrovia-s12-production-smoke.mjs`,
`umrovia-s12-production-light.png`, `umrovia-s12-production-mobile.png`.

Rekening platform di konfigurasi lokal masih kosong; UI dengan benar
menonaktifkan pembuatan top-up nyata.
Isi tiga `WALLET_MANUAL_*` environment variables dan recreate API bila akun
platform sudah tersedia. Tidak mengisi rekening fiktif pada stack aplikasi.

## Batas S12

S12 menyediakan primitive debit **internal**, bukan consumer DP event.
S13 akan membuat charge unit/tarif snapshot, mengonsumsi event secara idempoten,
retry pending FIFO setelah top-up dan menangani kompensasi/reversal. Milestone
monetisasi M4 belum ditutup oleh S12; top-up tidak otomatis mengonfirmasi peserta.
Keputusan DP S11 (>Rp0 verified, target minimum opsional) tetap berlaku.

Gateway live belum dihubungkan sesuai pilihan manual. Evidence masih lokasi/
referensi dokumen, belum upload/scan. Platform console menyeluruh mengikuti
S18; staf billing menggunakan API review/settlement berizin. Scheduler umum
menyusul; command rekonsiliasi siap dijadwalkan harian oleh operator. Tidak ada
edit/delete ledger, fee/pajak implisit, minimum top-up baru, atau automatic refund.
