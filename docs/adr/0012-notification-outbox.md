# ADR-0012 — Notifikasi: outbox transaksional, antrean, retry dan template

Tanggal: 26 Oktober 2026. Status: accepted. Sprint S16 (Roadmap §3: "Email
notifications, retries, templates"; gate "Queue/idempotency tests").
PRD §51.4 FT-04 (NTF-01…05), Product Spec §5.5, §7.6, §11, UI-14, NTF01, TR07.

## Keputusan

### Outbox = tabel notifikasi

Hook event bisnis menulis baris `notifications_notification` **di transaksi
yang sama** dengan perubahan bisnis. Bila transaksi gagal, notifikasi ikut
batal; bila commit, pesan pasti tercatat. Tidak ada tabel event perantara
yang perlu dipoll ulang: baris notifikasi sekaligus menjadi log pengiriman.

Unique key `(tenant, source_key, template_key, channel, recipient_type,
recipient_id)` (Spec §5.5) menjamin **satu pesan logis per event per penerima
per kanal** walau event diproses ulang (verifikasi ulang, issue invoice ulang,
job terjadwal berjalan dua kali).

Hook dibungkus savepoint dan menelan error (dicatat tanpa PII) sehingga
kegagalan notifikasi tidak membatalkan DP, kuitansi atau charge (NTF-04).

### Event dan penerima

| Event | source_key | Penerima |
|---|---|---|
| Booking → RESERVED | `booking:{id}` | Jamaah peserta |
| Invoice terbit | `invoice:{id}` | Jamaah per baris, nominal miliknya sendiri |
| Pembayaran terverifikasi (+ kuitansi) | `payment:{id}` | Jamaah yang dialokasikan |
| Pembayaran lunas | `payment:{id}` (template `payment.settled`) | Jamaah yang sisa tagihannya 0 |
| Dokumen disetujui/ditolak | `document:{id}` | Jamaah pemilik, beserta alasan |
| Jadwal berubah (tanggal, kota, titik kumpul, rute) | `departure:{id}:{updated_at}` | Peserta aktif keberangkatan |
| Charge SaaS tertunda | `saas.charge.pending:{charge}` | Owner travel |
| Pengingat trial H-7/H-3/H-1 | `trial:{id}:d{n}` | Owner travel |

Kanal jamaah: portal (selalu) + email (produksi dan bila jamaah punya email).
Di environment demo, kontak jamaah **tidak pernah** diemail; subjek diberi
`[DEMO]`. Owner (akun terverifikasi) tetap menerima email.

Pesan untuk satu jamaah dalam booking grup hanya memuat data miliknya
(nominal baris, alokasi, sisa tagihan). Pesan tidak pernah memuat NIK, paspor
atau lampiran dokumen; hanya tautan portal yang memerlukan login.

### Antrean dan worker

`notifications_notificationjob` adalah tabel platform berisi ID saja (pola
`wallet_gatewayorder`) sehingga worker dapat menemukan pekerjaan lintas tenant
tanpa melewati RLS. Untuk setiap job worker:

1. mengklaim dengan `SELECT … FOR UPDATE SKIP LOCKED` dan menggeser `due_at`
   sebagai lease (`NOTIFICATION_LEASE_SECONDS`), sehingga worker paralel tidak
   mengambil job yang sama;
2. membaca notifikasi di konteks RLS tenant, lalu mengirim SMTP **di luar**
   transaksi DB;
3. menandai `SENT`, atau `FAILED` dengan jadwal ulang dari
   `NOTIFICATION_RETRY_DELAYS` (bawaan 1 m, 5 m, 30 m, 2 j); setelah habis
   → `DEAD` (dead-letter). Hanya nama kelas error yang disimpan.

Pengiriman bersifat at-least-once: worker yang mati setelah SMTP sukses tetapi
sebelum commit dapat mengirim ulang setelah lease habis. Staf dapat
**mengirim ulang** email (`FAILED/DEAD/SENT`) dengan isi tersimpan yang sama;
tercatat di audit `notifications.resent`.

`run_worker` (service `worker` di Docker Compose) menjalankan antrean tiap
`WORKER_INTERVAL_SECONDS` serta job terjadwal: `expire_trials` dan
`send_trial_reminders` (per jam), `retry_pending_charges` (15 menit). Semua job
idempoten.

### Template

Template bawaan berada di kode (`catalog.py`) dengan variabel
`{{ nama_variabel }}`. Travel dapat mengubah subjek/isi template jamaah;
validasi menolak variabel tak dikenal, variabel wajib yang dihapus, dan subjek
multi-baris (cegah header injection). Setiap perubahan atau reset menaikkan
versi; notifikasi menyimpan versi dan teks hasil render. Template untuk owner
(charge tertunda, trial) milik platform dan tidak dapat diubah. Footer
identitas travel ditambahkan sistem.

Email dikirim dari `DEFAULT_FROM_EMAIL` dengan nama tampilan
"{Travel} via Umrovia", header `Auto-Submitted: auto-generated`.

### Akses

`notifications.read` (Owner, Admin, Finance, Operations): log dan template.
`notifications.manage` (Owner, Admin): ubah template dan kirim ulang. Migrasi
`tenants.0008` menambah grant hanya pada role default yang belum diubah.
Email penerima ditampilkan tersamar di log. Inbox portal
(`/portal/notifications`) memakai grant `PortalAccess` dan hanya menampilkan
pesan untuk jamaah grant tersebut.

## Di luar cakupan

WhatsApp/SMS (P1), preferensi pesan non-transaksional (seluruh pesan MVP
bersifat transaksional), email HTML, webhook bounce/complaint provider, dan
antrean ekspor manifest asinkron (ekspor masih sinkron).
