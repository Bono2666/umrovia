# UAT operasional — Sprint S15

Gate Roadmap S15: **Operational UAT**. Skenario di bawah dijalankan oleh
admin operasional travel pada workspace produksi (atau demo untuk TR05).
Setiap skenario punya pembuktian otomatis; kolom "Uji manual" berisi langkah
untuk penerimaan oleh pengguna.

| ID | Skenario | Uji manual | Hasil yang diharapkan | Bukti otomatis |
|---|---|---|---|---|
| OPS01 | Dua staf berebut kursi terakhir | Kapasitas 1, dua staf mereservasi booking bersamaan | Satu berhasil, satu ditolak; kursi tidak melebihi kapasitas | `test_departures.py::test_uat02_two_staff_race_for_last_seat`, `test_booking.py` |
| OPS02 | Tandai Siap berangkat tanpa dokumen wajib | Keberangkatan → Tandai siap berangkat saat ringkasan menunjukkan kekurangan | Ditolak; hanya "Siap dengan pengecualian" beralasan yang lolos dan tercatat di audit | `test_manifest.py` (gerbang READY + exception) |
| OPS03 | Ekspor data pribadi oleh peran tanpa izin | Login sebagai Operasional → Manifest → centang data pribadi → PDF/Excel/CSV, atau formulir dengan NIK lengkap | 403 dan tercatat `manifest.export_denied` / `manifest.print_denied` | `test_operations.py::test_pii_exports_require_permission_and_are_audited`, `::test_print_permissions_pii_and_unknown_kind`, `test_manifest.py` |
| OPS04 | Manifest PDF/XLSX/CSV dengan versi | Manifest → PDF/Excel/CSV; Publikasikan versi → Unduh PDF versi | Isi sama dengan filter tampilan; versi mencantumkan nomor, waktu dan penerbit; snapshot dimanipulasi ditolak | `test_operations.py::test_xlsx_export_masked_by_default_and_formula_safe`, `::test_published_version_pdf_from_verified_snapshot` |
| OPS05 | Pembayaran per jamaah di manifest | Filter Pembayaran: Lunas / Sebagian / Belum bayar | Hanya jamaah sesuai status; nominal terbayar dan sisa sesuai pembayaran terverifikasi | `test_operations.py::test_manifest_rows_carry_payment_status_and_filters` |
| OPS06 | Ringkasan kesiapan keberangkatan | Keberangkatan → Manifest & cetak | Jumlah dokumen lengkap, DP diterima, lunas, terkonfirmasi, kursi, piutang dan kekurangan checklist; tidak berubah oleh filter | `test_operations.py::test_readiness_summary_ignores_filters` |
| OPS07 | Dokumen cetak MOD-12 | Cetak dokumen → Formulir pendaftaran, Label koper, Amplop | PDF per jamaah aktif; formulir tersamar kecuali pemegang izin data pribadi | `test_operations.py::test_print_documents` |
| UAT-14 | Manifest hanya peserta keberangkatan | Bandingkan roster dua keberangkatan | Peserta booking batal/kedaluwarsa dan keberangkatan lain tidak muncul; keberangkatan tenant lain 404 | `test_manifest.py`, `test_operations.py::test_other_tenant_departure_is_not_found` |
| TR05 | Dokumen demo | Workspace demo → ekspor/cetak | Nama berkas diawali `DEMO-` dan PDF ber-watermark "DEMO — BUKAN DOKUMEN RESMI" | `test_operations.py::test_demo_documents_are_watermarked` |

## Catatan penerimaan

- Ekspor XLSX menjaga teks yang diawali `=`, `+`, `-` atau `@` sebagai teks,
  bukan formula.
- Semua unduhan `attachment`, `no-store`; ekspor dan cetak tercatat di audit
  beserta format, flag data pribadi, jumlah baris dan filter.
- Rooming list, visa, tiket dan itinerary (OPS-07) tetap P1 di luar UAT ini.
