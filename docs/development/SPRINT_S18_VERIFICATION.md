# Verifikasi Sprint S18

Tanggal: 27 Oktober 2026. Status: **DONE** untuk exit gate S18
("Admin MFA/audit, no PII leakage"). Branch: `sprint/s18-platform-console`.
Keputusan desain: [ADR-0014](../adr/0014-platform-control-plane.md).

## Pengujian otomatis

- Suite backend lengkap: **418/418 lulus** (438 detik), termasuk 12 kasus baru
  di `tests/test_platform_console.py`. Fixture platform lama (settle top-up,
  refund) kini memakai sesi ber-MFA; dua test wallet disesuaikan dengan
  perilaku baru (tenant ditangguhkan → 403, non-staf ditolak sebelum metode).
- TOTP cocok dengan vektor uji RFC 6238.
- MFA: password salah ditolak; secret tersimpan terenkripsi; kode salah
  ditolak; 10 kode pemulihan (hanya hash tersimpan); konsol 403
  `mfa_required` sebelum verifikasi dan pada sesi baru; kode TOTP yang sama
  tidak bisa dipakai ulang; kode pemulihan sekali pakai; TTL sesi berlaku;
  perangkat aktif tidak bisa ditimpa; reset lewat perintah; audit lengkap,
  termasuk percobaan gagal.
- Peran: Owner tenant 403; staf tanpa grup 403; Support tidak bisa suspend,
  audit atau billing; Billing tidak bisa suspend, tiket atau tarif.
- Tanpa PII: ringkasan, daftar dan detail tenant, trial, audit, tarif, daftar
  dan detail tiket tidak memuat nama, NIK, email atau telepon jamaah, maupun
  email owner lengkap; membuka detail tenant tercatat.
- Lifecycle: alasan < 10 karakter 400; suspend menutup API operasional
  (`tenant_suspended`) dan portal jamaah, sementara `/me` dan Bantuan tetap
  bisa; aktifkan kembali memulihkan; konversi trial saat ditangguhkan tidak
  membuka akses; terminate ditolak tanpa suspend, ditolak bila diputuskan
  pengaju, disetujui admin kedua → `tenant_terminated`, tidak bisa
  diaktifkan kembali.
- Trial: perpanjang 1–30 hari beralasan → EXTENDED + event trial.
- Tarif: tanggal lampau dan kode ganda ditolak; tarif berlaku tidak berubah;
  Billing tidak bisa menerbitkan tarif.
- Tiket: validasi, catatan internal tersembunyi dari travel, balasan
  mengantrekan email (tanpa awalan DEMO), balasan travel membuka ulang,
  tandai selesai, isolasi antar travel (404).
- Ringkasan & antrean billing: pendapatan bulan ini (biaya terpotong −
  refund disetujui), kewajiban saldo wallet, top-up dan refund menunggu;
  antrean tanpa nama jamaah.
- Ruff, ESLint, TypeScript dan `makemigrations --check` bersih.

## Browser

Playwright + Chrome, database fiktif `umrovia_plat_ui`:

- Staf masuk → diarahkan ke `/platform` → daftar MFA (password, kunci,
  kode TOTP dihitung skrip) → 10 kode pemulihan → konsol.
- Ringkasan → Tenant → detail → **tangguhkan** beralasan.
- Owner travel melihat panel "Workspace ini sedang ditangguhkan" dan tetap
  bisa membalas tiket di Bantuan.
- Admin mengaktifkan kembali, memverifikasi top-up Rp500.000 di Billing, dan
  membalas tiket (diagnosis tanpa data jamaah). Audit memfilter tindakan
  platform; halaman Tarif tampil.
- Setelah `reset_platform_mfa`: daftar ulang, verifikasi dengan kode
  pemulihan, verifikasi TOTP di ponsel 390 px tanpa scroll horizontal.
  Tidak ada pageerror.

Perbaikan dari QA: riwayat tindakan di detail tenant kini mengecualikan
catatan "dilihat" (tetap ada di Audit).

Build produksi (`next build`, juga di image Docker) awalnya gagal pada route
dinamis `/platform/tenant/[id]`: dengan `cacheComponents`, `usePathname()` di
shell wajib berada di dalam `<Suspense>`. Layout konsol kini membungkus shell
dengan Suspense; build lokal dan image Docker berhasil.

## Batas S18

Elevasi akses support ke data tenant, passkey, MFA untuk role keuangan
tenant, QR code pendaftaran, dan host admin terpisah belum termasuk (S19 /
backlog).
