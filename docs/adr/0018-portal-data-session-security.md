# ADR-0018 — Keamanan sesi, portal, data jamaah dan varian harga

Tanggal: 27 Oktober 2026. Status: accepted. Menutup gap P0 G9–G13 dan sisa
G8 (laporan Jamaah) di [audit P0](../development/P0_GAP_AUDIT.md): PRD
AUTH-02/03/05, POR-05/06, MOD-04, MOD-05, MOD-08, MOD-13.

## Keputusan

- **Sesi (AUTH-02/03).** Middleware `SessionSecurityMiddleware`: sesi berakhir
  setelah `SESSION_IDLE_SECONDS` (default 2 jam) tanpa aktivitas dan paling lama
  `SESSION_ABSOLUTE_SECONDS` (default 12 jam) sejak masuk. Aktivitas
  memperpanjang sesi paling sering tiap 5 menit (tanpa tulis sesi tiap request).
  `User.session_version` disimpan saat login; "Keluar dari semua perangkat",
  reset sandi, dan "Akhiri semua sesi" oleh Owner menaikkan versi sehingga sesi
  lama ditolak.
- **Audit login (AUTH-05).** Login sukses/gagal, logout, logout semua perangkat,
  reset sandi dicatat di audit (perangkat & IP; email tak dikenal tetap
  dicatat tanpa objek). Pengguna melihat riwayatnya di "Akun Saya"; Owner
  melihat riwayat anggota dan dapat menangguhkan/mengaktifkan kembali,
  mengirim reset sandi, atau mengakhiri semua sesi (`memberships.manage`).
  Owner terakhir tidak dapat ditangguhkan.
- **Pengumuman portal (POR-05).** `portal.Announcement` per environment untuk
  semua jamaah atau satu keberangkatan; draf/tayang/berakhir; tampil di portal
  hanya untuk jamaah dengan booking aktif pada keberangkatan tersebut.
  Izin `announcements.manage` (Admin, Operations).
- **Koreksi identitas (POR-06).** Jamaah mengajukan koreksi nama, tanggal/tempat
  lahir, NIK, paspor dari portal dengan alasan; nilai baru divalidasi seperti
  input staf dan disimpan **terenkripsi**, tampilan memakai nilai termask.
  Satu permintaan menunggu per jamaah. Staf `pilgrims.write` menyetujui
  (diterapkan ke data jamaah, termasuk deteksi duplikat NIK) atau menolak
  dengan alasan yang terlihat jamaah.
- **Data jamaah (MOD-04).** Kelompok keluarga dengan hubungan (satu kepala
  keluarga); riwayat perjalanan jamaah (booking, keberangkatan, harga,
  terbayar, dokumen, koreksi); ekspor daftar jamaah CSV/XLSX (`pilgrims.export`,
  Admin) termask, NIK/paspor lengkap hanya dengan `reports.export_pii` (Owner);
  setiap ekspor diaudit dan CSV dinetralkan dari injeksi formula.
- **Varian harga (MOD-05).** Paket dapat menawarkan harga anak tanpa kasur
  (< 12 tahun saat berangkat) dan bayi (< 2 tahun), layanan tambahan (kode,
  nama, harga per jamaah) dan estimasi biaya per jamaah untuk estimasi margin.
  Kategori dan layanan tambahan ikut disnapshot per peserta; baris harga
  `addon` dan invoice mencantumkannya; komisi memakai harga bersih termasuk
  layanan tambahan. Usia divalidasi bila tanggal lahir diketahui.
- **Dokumen (MOD-08).** `PilgrimDocument.valid_from/expires_at` diisi saat
  review; dokumen yang sudah kedaluwarsa tidak dapat disetujui. Pengingat
  Ringkasan dan laporan Jamaah menandai dokumen yang kedaluwarsa sebelum
  tanggal berangkat. Pemindai antimalware tetap butir infrastruktur
  (GO_LIVE_CHECKLIST).
- **Laporan Jamaah (MOD-13).** Per keberangkatan: status peserta, kamar,
  kelengkapan & masa berlaku dokumen, status bayar, sisa tagihan, kesiapan.

## Konsekuensi

- Tabel baru (`portal_announcement`, `portal_profilechangerequest`,
  `pilgrims_familygroup`) ber-RLS ENABLE+FORCE; izin baru via `tenants.0015`.
- Sesi yang dibuat sebelum rilis ini diberi versi pada request berikutnya,
  sehingga tidak ada logout massal saat deploy.
