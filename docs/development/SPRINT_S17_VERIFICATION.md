# Verifikasi Sprint S17

Tanggal: 27 Oktober 2026. Status: **DONE** untuk exit gate S17
("Reconciliation vs primary records"). Branch: `sprint/s17-reports`.
Keputusan desain: [ADR-0013](../adr/0013-ready-reports.md).

## Pengujian otomatis

- Suite backend lengkap: **406/406 lulus** (562 detik), termasuk 9 kasus baru
  di `tests/test_reports.py`. Tiga test migrasi role diperbarui agar ikut
  menjalankan `tenants.0009`.
- RPT01: invoice terbit, pembayaran bersih (bruto − reversal), piutang dan
  pengeluaran pada laporan sama dengan agregat langsung dari
  `TravelInvoice`, `TravelPayment` dan `TravelExpense`; pengeluaran yang
  dibatalkan tidak dihitung; semua cek rekonsiliasi `ok`.
- Kas/bank: per rekening dan tunai (masuk, reversal, pengeluaran, saldo
  akhir); periode berikutnya membawa saldo awal yang benar.
- Margin estimasi: penjualan − biaya per keberangkatan; tetap tampil pada
  periode bulan berjalan walau keberangkatan bulan depan.
- RPT02: statement SaaS Wallet (saldo awal + top-up + refund − debit) sama
  dengan `balance_after` ledger; top-up wallet tidak masuk kas travel, dan DP
  tidak masuk laporan wallet.
- Operasional: kapasitas, kursi, okupansi, booking, DP, checklist, manifest;
  cek kursi = peserta booking aktif; filter paket/status; input tidak valid
  (paket asing, status, rentang terbalik/terlalu panjang, format tanggal) 400;
  jenis laporan tak dikenal 404.
- Ekspor PDF/XLSX/CSV: konten, nama berkas, `no-store`, audit
  `reports.exported`; nilai CSV berawalan formula diberi tanda kutip; demo
  berprefiks `DEMO-`.
- Izin: Operations hanya operasional; Finance semua laporan + pengeluaran;
  Sales ditolak. Pengeluaran: tanggal masa depan, keberangkatan/rekening
  asing, nominal 0, kategori salah → 400; batal idempoten dan beralasan;
  `save()`/`delete()` model ditolak. RLS tabel pengeluaran; tenant lain tidak
  melihat angka atau mengakses pengeluaran (404).
- Ruff, ESLint, TypeScript dan `makemigrations --check` bersih.

## Browser

Playwright + Chrome pada API nyata dengan database fiktif `umrovia_rpt_ui`
(dua keberangkatan, DP perorangan dan grup, empat pengeluaran + satu batal,
top-up wallet Rp200.000 yang memotong tiga biaya layanan):

- Operasional: 2 keberangkatan, okupansi 3,5%, checklist "Kurang 6",
  rekonsiliasi sesuai.
- Keuangan: invoice Rp104,5 jt, penerimaan Rp30 jt, piutang Rp74,5 jt,
  pengeluaran Rp78,5 jt, margin estimasi 27,3%; semua cek sesuai; unduhan
  PDF, Excel, CSV berhasil dan PDF diperiksa visual.
- SaaS Wallet: saldo Rp50.000 = top-up Rp200.000 − 3 × Rp50.000.
- Pengeluaran: catat (total naik) lalu batalkan (total kembali).
- Tampilan 390 px tanpa scroll horizontal; tidak ada pageerror.

Perbaikan dari QA: margin sempat kosong untuk periode bulan berjalan
(cakupan diperluas ke keberangkatan dengan invoice/biaya dalam periode),
angka rekonsiliasi diformat rupiah, dan zona waktu ganda di kepala PDF dihapus.

## Batas S17

Laporan keuangan formal (P1), impor/rekonsiliasi mutasi bank, cabang, dan
laporan platform (S18) belum termasuk. Ekspor tetap sinkron dengan batas 500
baris per daftar.
