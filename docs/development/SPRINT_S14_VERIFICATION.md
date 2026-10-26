# Verifikasi Sprint S14

Tanggal: 26 Oktober 2026. Status: **DONE** untuk exit gate S14
("Object-level permissions"). Branch: `sprint/s14-pilgrim-portal`.
Desain: [ADR-0011](../adr/0011-pilgrim-portal.md).

## Pengujian otomatis

- Suite backend lengkap: **373/373 lulus** (473 detik), termasuk 17 kasus
  baru di `tests/test_portal.py`. Setelah penyesuaian teks batas waktu,
  test portal, jamaah dan manifest diulang: 46/46 lulus.
- Undangan: email terkirim, inspeksi tersamar, password lemah ditolak tanpa
  menghabiskan undangan, sekali pakai, undangan lama dicabut saat diganti,
  token palsu/tak dikenal/kedaluwarsa ditolak, kegagalan SMTP → 502 dan
  undangan tidak tersimpan.
- Akun terdaftar wajib login sebagai email undangan; akun lain ditolak.
- Object-level (POR02): portal hanya menampilkan peserta sendiri; nama jamaah
  lain dalam booking grup tidak muncul; grant milik orang lain atau UUID acak
  404; PDF invoice grup 404; booking solo dapat mengunduh invoice/kuitansi.
- Dokumen (POR01): unggah PDF/PNG/JPEG, versi bertambah setelah ditolak,
  alasan terlihat, dokumen APPROVED tidak dapat diganti (409). Executable,
  teks, PDF ber-JavaScript, berkas kosong, jenis tak dikenal dan berkas di
  atas batas ditolak tanpa catatan dokumen.
- Signed download (SEC02): unduhan pemilik 200 + header aman; sesi lain 404;
  anonim ditolak; token diubah 404; lewat 10 menit 403; setelah akses dicabut
  404 walau token masih berlaku; setiap unduhan diaudit.
- Staf: unggah, tautan unduh cakupan staf, peran tanpa `pilgrims.write` tidak
  dapat mengundang. Environment read-only menolak unggah/ubah profil.
- RLS ENABLE+FORCE pada `portal_portalinvite`. Migrasi clean → rollback
  (`portal zero`) → reapply lulus. Ruff, ESLint dan TypeScript bersih.

## Browser (Playwright + Chrome, API nyata, database terpisah)

Database fiktif `umrovia_portal_ui`, email ditulis ke file. Alur: Owner
membuka detail Ahmad Fauzi → kirim undangan → tautan dari email → buat
password → portal menampilkan jadwal, langkah progres, tagihan Rp36.500.000,
terbayar Rp10.000.000, sisa Rp26.500.000, invoice dan kuitansi solo; anggota
rombongan lain tidak tampil → unggah paspor PDF → staf melihat berkas (unduh
`passport-v1.pdf`) dan menolak dengan alasan → jamaah melihat alasan,
mengunduh dan mengunggah ulang (riwayat 2 versi) → akun jamaah diarahkan dari
`/dashboard` ke `/portal` → login dengan `?next=/portal` → mobile 390 px tanpa
overflow. Tidak ada pageerror. Perbaikan dari QA: teks batas waktu, jarak
label kartu profil, dan pilihan "unggah dokumen lain" yang tampak nonaktif.

## Batas S14

Pemindai antimalware belum tersedia (mitigasi: allowlist magic bytes, tolak
PDF aktif, attachment-only, review petugas). Notifikasi portal dan email
berbasis event → S16. Penyimpanan memakai storage default (volume privat);
bucket S3 privat/presign menyusul pemilihan object storage produksi.
