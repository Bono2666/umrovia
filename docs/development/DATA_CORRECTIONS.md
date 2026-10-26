# Koreksi data pada workspace travel

Tanggal: 26 Oktober 2026. Branch: `feat/data-corrections`.

## Cara menggunakan

Pilih data pada daftar, klik **Ubah**, lakukan koreksi, lalu **Simpan
perubahan**. **Batal ubah** keluar dari mode edit tanpa mengirim perubahan.
Form memakai data tersimpan saat ini; kesalahan ditampilkan di halaman agar
isian tidak hilang. Tombol koreksi mengikuti izin akun dan environment aktif.
Data demo yang sudah read-only tetap dapat dilihat.

| Halaman | Tindakan dan cakupan koreksi |
|---|---|
| Jamaah | **Ubah jamaah**: identitas profil, kontak, wali/mahram, kontak darurat, kebutuhan khusus, data paspor dan status aktif/arsip. |
| Paket | **Ubah paket / harga**: nama, jenis, durasi, harga standar/kamar, deskripsi, fasilitas, ketentuan pembayaran dan pembatalan. Harga booking/invoice lama tetap. |
| Keberangkatan | **Ubah keberangkatan**: paket sebelum ada booking, PIC, jadwal, kota/rute, meeting point, kapasitas/blokir, batas pendaftaran dan catatan. |
| Booking | **Ubah booking** pada status **Draf**: keberangkatan, peserta, kamar dan catatan. Booking yang sudah reservasi memakai alur status/pembatalan. |
| Kas & Bank | **Ubah rekening**: nama bank/pemilik dan status aktif. Nomor dapat dikoreksi selama belum pernah dipakai pada pembayaran. |
| Pengguna & Role | **Ubah peran** pada anggota, pilih peran dan simpan secara eksplisit. **Ubah definisi peran** mengubah nama/izin role custom yang tidak dilindungi. |
| Profil Travel | Koreksi tiap bagian, **Simpan**, atau **Batal ubah** untuk mengembalikan nilai tersimpan bagian tersebut. |

### NIK, paspor dan rekening

Nomor sensitif tidak diisikan ulang dari nilai masked. Pada mode edit,
**kolom pengganti yang kosong mempertahankan nomor lama**. Isi nomor baru
bila memang ingin mengganti. Untuk menghapus NIK/paspor yang salah, pilih
checkbox hapus tersimpan, lalu simpan. Respons tetap masked; audit tidak
menyimpan nomor penuh.

Nomor rekening yang sudah muncul pada pembayaran dikunci, termasuk pembayaran
draf/ditolak yang tetap merupakan histori. Jika nomor berubah, nonaktifkan
rekening lama dan tambahkan rekening baru. Nama/pemilik dapat dikoreksi tanpa
mengubah PDF invoice/kuitansi yang sudah diterbitkan.

### Data yang sudah dipakai

- Paket keberangkatan dikunci sejak ada booking, termasuk booking draf,
  agar referensi perjalanan/harga tidak berubah diam-diam. Buat keberangkatan
  baru untuk paket berbeda.
- Pada keberangkatan DEPARTED/COMPLETED/CANCELED, jadwal, paket dan kuota
  dikunci. Informasi operasional dan catatan masih dapat dikoreksi.
- Kapasitas tidak dapat lebih kecil dari kursi terpakai + blokir. Koreksi
  keberangkatan mengunci baris yang sama dengan reservasi kursi.
- Koreksi booking mempertahankan UUID peserta dan snapshot harga untuk peserta
  yang tetap dengan kamar/keberangkatan sama. Perubahan kamar/keberangkatan
  memakai tarif terkini; invoice terbit tidak diubah.
- Perubahan nama/email akun global bukan bagian dari form keanggotaan tenant.
  Form pengguna mengelola peran dalam travel terkait. Role Owner/sistem
  dilindungi; pengelola tidak dapat menambahkan izin di luar haknya sendiri.
- Pembayaran terverifikasi menggunakan reversal/koreksi terpisah. Invoice,
  kuitansi dan ledger wallet tetap mengikuti aturan immutable yang sudah ada.

## Bukti implementasi dan verifikasi

- Backend: `PATCH` jamaah/keberangkatan/rekening dikunci secara transaksional;
  pengambilan rekening saat record payment ikut memakai lock yang sama.
  Validasi paspor mempertimbangkan tanggal lama saat PATCH satu field saja.
- `/me` menampilkan `writable_environments` dari state environment server;
  UI menyembunyikan editor tanpa izin atau pada data read-only. Backend
  tetap memvalidasi tenant, izin, environment dan status.
- PATCH frontend mengirim field yang dikoreksi, dengan nomor sensitif
  dikelola eksplisit. `datetime-local` dikonversi ke ISO ber-offset agar
  jam keberangkatan tidak bergeser saat dibuka dan disimpan.
- Definisi role custom dapat dikoreksi atau dikosongkan izinnya; grant baru
  hanya dalam scope actor. Role Owner legacy tanpa flag sistem juga terkunci.
- Tidak ada perubahan skema database; `makemigrations --check` dan Django
  system check lulus.
- **303/303 test backend lulus**, 0 gagal/error/skipped, mencakup 13 kasus
  baru koreksi data dan seluruh regresi S01–S12. Laporan:
  `/private/tmp/umrovia-corrections-full.xml` (413 detik).
- Targeted correction + staff/admin: **52 lulus**. Ruff, ESLint, TypeScript
  dan `git diff --check` lulus.
- Browser Chrome/Playwright menggunakan API nyata dan database fiktif
  `umrovia_corrections_ui`, bukan database aplikasi. Ketujuh form diuji
  save/cancel; jamaah mempertahankan NIK/paspor/kebutuhan khusus; waktu
  keberangkatan tetap; booking menjaga peserta/harga dan terkunci sesudah
  reservasi; nomor rekening terpakai menjadi disabled; anggota/role/profil
  tersimpan; akun pembaca tidak melihat editor. Dark/mobile tanpa overflow
  dan tanpa pageerror. Artefak: `/private/tmp/umrovia-corrections-browser.mjs`,
  `umrovia-corrections-browser.log`, `umrovia-corrections-mobile.png`.
- Runtime browser bawaan tidak tersedia; panduan browser telah dibaca sebelum
  fallback ke Playwright yang sudah terpasang dengan Chrome lokal.

- Build Docker API/web dan TypeScript produksi lulus (25 route). API, DB
  dan Redis healthy; seluruh halaman koreksi HTTP 200, system check dan
  migrate check lulus. Hash 9 file backend yang berubah cocok dengan source
  pada API yang berjalan. Bukti: `/private/tmp/umrovia-corrections-build.log`,
  `umrovia-corrections-web-final-build.log`, `umrovia-corrections-runtime.log`.
- Smoke Chrome pada build produksi localhost:3000 lulus untuk simpan koreksi,
  hapus NIK eksplisit setelah input pengganti tidak valid, mempertahankan
  paspor/kebutuhan khusus, dark/mobile tanpa overflow dan tanpa pageerror.
  Seluruh API smoke produksi diintersep fixture; tidak menulis data aplikasi.
  Artefak: `/private/tmp/umrovia-corrections-production-check.mjs`,
  `umrovia-corrections-production-check.log`, `umrovia-corrections-production-mobile.png`.
- API/frontend QA dihentikan dan database QA dihapus setelah verifikasi.
  Seluruh bukti tetap tersedia di `/private/tmp`.

Perubahan ini belum di-commit/push.
