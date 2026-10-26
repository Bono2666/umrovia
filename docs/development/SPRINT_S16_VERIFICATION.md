# Verifikasi Sprint S16

Tanggal: 26 Oktober 2026. Status: **DONE** untuk exit gate S16
("Queue/idempotency tests"). Branch: `sprint/s16-notifications`.
Keputusan desain: [ADR-0012](../adr/0012-notification-outbox.md).

## Pengujian otomatis

- Suite backend lengkap: **397/397 lulus** (581 detik), termasuk 13 kasus baru
  di `tests/test_notifications.py`. Dua test migrasi role lama diperbarui agar
  ikut menjalankan migrasi `tenants.0008` (default role kini memuat grant
  notifikasi).
- RLS ENABLE+FORCE pada `notifications_notification` dan
  `notifications_notificationtemplate`; tabel antrean hanya berisi ID.
- Idempotensi: booking/invoice/pembayaran diproses ulang tidak menambah pesan;
  verifikasi ulang pembayaran tidak menambah email; pengingat trial dijalankan
  dua kali tetap satu pesan per hari × penerima (TR07).
- Antrean: klaim kedua tidak mendapat job yang sedang di-lease; worker
  mengirim tepat sekali lalu menghapus job.
- NTF01: SMTP gagal → `FAILED` dengan jeda 60 detik, berikutnya sesuai jadwal,
  habis → `DEAD`; pembayaran tetap `VERIFIED`; kirim ulang memakai isi yang sama
  dan tercatat di audit. Hook yang error tidak menggagalkan verifikasi DP.
- Isi pesan: nominal milik jamaah sendiri dalam booking grup, alasan penolakan
  dokumen, daftar perubahan jadwal; demo tidak mengirim email ke kontak jamaah
  dan subjek berawalan `[DEMO]`.
- Template: variabel wajib dihapus, variabel tak dikenal, dan subjek multi-baris
  ditolak 400; simpan → versi 2, reset → versi 3; template platform 404;
  Operations hanya baca, Sales 403.
- Log: filter, ringkasan status, email tersamar; tenant lain 404.
- Inbox portal hanya menampilkan pesan jamaah grant; tandai dibaca jamaah lain 404.
- Ruff, ESLint dan TypeScript bersih; `makemigrations --check` bersih.

## Browser dan worker

Playwright + Chrome pada API nyata dengan database fiktif `umrovia_ntf_ui`
(21 notifikasi dari event seed). Worker dijalankan dengan SMTP tak terjangkau
→ 11 email `Dicoba ulang`; halaman Notifikasi menampilkan ringkasan, isi pesan,
filter dan kirim ulang. Editor template: pratinjau, simpan (Disesuaikan,
versi 2), penolakan variabel wajib, reset (versi 3), template platform hanya
baca. Portal jamaah: inbox "4 baru", baca pesan perubahan jadwal, tandai semua
dibaca; tampilan ponsel 390 px rapi. Tidak ada pageerror.

Perbaikan dari QA: kolom isi template semula hanya dua baris (CSS form
workspace) → kelas `textarea-tall` 320 px.

Worker sungguhan pada database yang sama dengan backend console: 11 email
terkirim dari "Amanah Tour via Umrovia", antrean kosong, status `SENT`.
Docker Compose: service `worker` berjalan dan menjalankan job terjadwal.

## Batas S16

WhatsApp/SMS tetap P1. Email berupa teks biasa. Bounce/complaint provider dan
preferensi pesan non-transaksional belum ada (seluruh pesan MVP transaksional).
Antrean ekspor manifest asinkron belum dikerjakan; ekspor tetap sinkron.
