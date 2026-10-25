# Audit penyelesaian Sprint S07–S10

Tanggal: 25 Oktober 2026. Ruang lingkup: 32 task pada `SPRINT_TRACKING.md`
dan exit gate dasar empat sprint. Dokumen PRD, Product Spec dan Roadmap
baseline tetap menjadi rujukan; tabel TODO pada Roadmap adalah baseline
perencanaan, sedangkan status implementasi dicatat di tracker pengembangan.

## Hasil per sprint

| Sprint | Task | Implementasi dan bukti | Hasil |
|---|---:|---|---|
| S07 | 8 | Master jamaah, enkripsi/masking NIK-paspor, duplikat, namespace dokumen, versi/review, RBAC/RLS/environment; halaman Jamaah; 11 test `test_pilgrims.py` | Lulus exit gate |
| S08 | 8 | Paket, keberangkatan, state machine, kuota dan reservasi atomik; 7 test katalog + 17 test keberangkatan, termasuk dua perlombaan kursi | Lulus exit gate |
| S09 | 7 | Booking multi-peserta, snapshot harga, kuota trial, reservasi/pelepasan kursi, status peserta, RBAC/RLS; 20 test booking termasuk dua booking mengambil kursi terakhir | Lulus exit gate |
| S10 | 9 | Checklist efektif, gerbang READY/DEPARTED, roster masked, filter, versi/checksum, CSV dengan PII berizin dan audit; 18 test manifest | Lulus exit gate |

Sebelas test audit tambahan mencakup regresi lintas-modul. Total suite
backend saat audit: **214 lulus, 0 gagal, 0 dilewati**. Dari jumlah tersebut,
84 test berada di modul S07–S10 dan regresi audit. Test dijalankan pada
PostgreSQL 18.4 lokal menggunakan database test terpisah, lalu database test
dihapus oleh pytest. Data aplikasi tidak digunakan sebagai fixture test.

## Temuan yang dilengkapi

1. Checklist global semula mengambil requirement dari seluruh environment
   tenant. `effective_requirements()` sekarang menyaring environment paket;
   dokumen demo tidak memengaruhi kesiapan booking/keberangkatan produksi.
   Regresi memeriksa kedua urutan pembuatan data dan respons manifest.
2. PIC semula menerima user global tanpa pemeriksaan membership aktif.
   Create/PATCH kini menolak user tenant lain, undangan yang belum aktif,
   dan akun suspended. Pemilih UI menggunakan `GET /api/v1/departures/staff`,
   dengan permission `departures.write`; respons hanya `id` dan `name`.
   Permission `memberships.read` tidak diperlukan untuk memilih PIC.
3. Formulir jamaah kini mengirim kewarganegaraan, status perkawinan, alamat,
   kontak darurat, wali/mahram, kebutuhan khusus dan metadata paspor.
   Detail mengambil `/pilgrims/{id}`, bukan mengandalkan list yang memang
   menghilangkan kebutuhan khusus. Permintaan detail lama dibatalkan secara
   logis ketika pemilihan jamaah berganti.
4. Halaman Keberangkatan menyediakan tindakan eksplisit “Siapkan dengan
   pengecualian”, dengan alasan wajib. Payload `checklist_exception: true`
   menggunakan guard dan audit yang sudah ada; gerbang DEPARTED tidak dilewati.
5. Review dokumen tanpa `status` sekarang menghasilkan 400 beserta
   `field_errors.status`, alih-alih kegagalan server. Versi dokumen terbaru,
   bukan versi lama yang sudah approved, dipakai untuk menentukan kesiapan.
6. `tenants/0005_operational_role_defaults` memperbarui role dengan grant
   yang persis cocok dengan baseline bawaan S05/S07/S08 menuju grant S10.
   Owner dan role kustom tidak diubah; Admin/Ops tidak mendapat
   `manifest.export_pii`. Migrasi memakai salinan grant historis yang beku,
   idempoten, dan rollback tidak menghapus grant yang sudah diterapkan.
7. `ManifestVersion.save()` untuk record existing serta `.delete()` ditolak;
   revisi normal diterbitkan sebagai versi baru. Guard ini berada pada model,
   mengikuti pola event/audit proyek; akses SQL administratif bukan bagian
   dari proteksi tersebut.
8. Volume Docker `api_media` dipasang ke MEDIA_ROOT container
   (`/backend/media`), sehingga snapshot tidak bergantung pada umur container.
   Pemeriksaan sebelum pembaruan menunjukkan tidak ada file media lama yang
   perlu dipindahkan.

## Verifikasi

- `pytest --junitxml=...`: 214/214 lulus; artefak hasil sesi tersedia pada
  `/private/tmp/umrovia-s07-s10-final.xml`.
- `ruff check backend`, `npm run lint`, `tsc --noEmit`, dan `git diff --check`
  lulus.
- Database audit kosong: `check`, `makemigrations --check --dry-run`, seluruh
  migrasi, rollback `tenants/0005` dan reapply lulus; tidak ada migrasi pending.
- Chrome dengan fixture contoh terisolasi: detail kebutuhan khusus, payload
  wali/kontak darurat/paspor, pilihan PIC, dan pengecualian dengan alasan lulus
  tanpa runtime error, baik pada server development maupun build Docker
  aktif di `localhost:3000`. Script sesi:
  `/private/tmp/umrovia-operational-ui-check.mjs`.
- Build Docker API dan web lulus, termasuk build Next.js dan TypeScript.
  API, PostgreSQL dan Redis healthy; halaman Jamaah, Keberangkatan dan
  Manifest merespons 200. Endpoint pemilih PIC menolak akses anonim (403).
- Runtime API: seluruh migrasi terpasang termasuk `tenants/0005`, tidak ada
  role baseline lama yang belum ditingkatkan, dan 10/10 tabel bisnis S07–S10
  memiliki RLS ENABLE+FORCE. Volume `umrovia_api_media` terpasang pada
  `/backend/media`.
- Startup lokal menggunakan `DEBUG=True`. Environment terminal membawa
  `DEBUG=False` tanpa SECRET_KEY produksi dan sempat menghentikan startup;
  layanan dipulihkan dengan konfigurasi development eksplisit. Konfigurasi
  produksi bukan bagian dari penerapan lokal ini.

## Batas ruang lingkup yang tetap terbuka

Selesainya empat sprint ini adalah kesiapan **operasional dasar**, bukan
seluruh fitur P0 MVP atau sign-off staging/produksi.

| Fitur | Tahap berikutnya |
|---|---|
| DP, invoice/kuitansi, aturan konfirmasi berbasis pembayaran, varian harga kamar | S11–S13 |
| Signed URL, unggah berkas nyata, MIME/ukuran/antivirus, portal jamaah | S14 |
| Manifest lanjutan, dokumen cetak serta PDF/XLSX | S15/S17 |
| Auto-expiry terjadwal, notifikasi, rekonsiliasi berkala | S16/S17 |
| FK dokumen per booking-participant, bukan master jamaah | Belum diimplementasikan; perlu keputusan kontrak data sebelum migrasi |
| Penanganan massal booking saat keberangkatan dibatalkan | Backlog operasional yang sudah dicatat pada S09 |

Dokumen tetap melekat pada master jamaah sesuai model PRD dan dipakai
untuk checklist peserta booking. Tidak ada klaim bahwa varian penyimpanan
per booking-participant atau fitur sprint lanjutan sudah tersedia.
