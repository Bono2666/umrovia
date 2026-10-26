# Verifikasi Sprint S15

Tanggal: 26 Oktober 2026. Status: **DONE** untuk exit gate S15
("Operational UAT"). Branch: `sprint/s15-departure-operations`.
Skenario UAT: [S15_OPERATIONAL_UAT.md](S15_OPERATIONAL_UAT.md).

## Pengujian otomatis

- Suite backend lengkap: **384/384 lulus** (488 detik) saat dijalankan
  tunggal, termasuk 11 kasus baru di `tests/test_operations.py`.
  Catatan: satu putaran yang berjalan bersamaan dengan subset test lain
  sempat gagal karena kedua proses berbagi database test; diulang tunggal,
  semua lulus.
- Manifest: status pembayaran (lunas/sebagian/belum), sisa tagihan, kamar,
  DP; filter pembayaran/booking dan validasi 400.
- Kesiapan: hitungan dokumen, DP, lunas, konfirmasi, piutang dan checklist
  tidak terpengaruh filter; berubah saat syarat dokumen ditambahkan.
- XLSX: header, data tersamar secara bawaan, teks berawalan `=` tetap teks.
- Data pribadi: PDF/XLSX/CSV dan formulir lengkap hanya untuk
  `manifest.export_pii`; penolakan 403 + audit; Sales tanpa `manifest.export`
  ditolak; format tidak dikenal 400.
- Versi terbit: PDF dari snapshot, versi tidak ada 404, snapshot dimanipulasi
  400 (checksum).
- Cetak: formulir, label, amplop (juga per booking), jenis tak dikenal 404.
- Demo: nama berkas `DEMO-…` dan watermark terpasang. Keberangkatan tenant
  lain 404 untuk ekspor, cetak dan versi.
- Ruff, ESLint dan TypeScript bersih. Tidak ada migrasi database baru.
  Dependensi baru: `openpyxl==3.1.5` (+ `et_xmlfile==2.0.0`) di lockfile.

## Browser dan dokumen

Playwright + Chrome pada API nyata dengan database fiktif `umrovia_ops_ui`:
Keberangkatan → "Manifest & cetak" → kartu kesiapan (0/3 dokumen, 1/3 DP,
piutang Rp94.500.000, 6 kekurangan) → filter pembayaran → unduh PDF, Excel,
CSV → cetak formulir, label, amplop → publikasikan versi → unduh PDF versi.
Tidak ada pageerror. Setiap PDF dirender ke gambar dan diperiksa: header
kolom manifest, identitas tersamar `•••• 0001`, amplop tanpa baris kosong.
Isi XLSX diperiksa (judul, filter cetak, kolom nominal numerik).

## Batas S15

Rooming list, visa, tiket dan itinerary tetap P1. Ekspor berjalan sinkron;
antrean `POST /exports` dan notifikasi perubahan jadwal menyusul S16;
laporan operasional S17.
