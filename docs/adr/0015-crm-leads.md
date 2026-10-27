# ADR-0015 — CRM & Lead (MOD-19) dibangun lebih awal

Tanggal: 27 Oktober 2026. Status: accepted. PRD MOD-19 (P2), US-015,
§42 (lead tidak billable). Diminta pemilik produk setelah S19 agar menu Leads
dapat dipakai sales.

## Keputusan

- Modul `crm`: `Lead` dan `LeadActivity`, data tenant ber-RLS ENABLE+FORCE,
  dipisah per environment (demo/produksi) seperti data operasional lain.
- Tahap NEW → CONTACTED → QUALIFIED → QUOTED → WON/LOST. Tahap terbuka boleh
  maju/mundur; LOST wajib alasan dan dapat dibuka kembali; WON **hanya** lewat
  konversi dan bersifat final. Aktivitas kontak pertama (WA/telepon/pertemuan)
  memindahkan NEW → CONTACTED. Setiap perubahan tercatat sebagai aktivitas dan
  audit.
- Follow-up: satu jadwal "berikutnya" per lead; filter "terlambat" dan "hari
  ini" memakai zona waktu travel; lead selesai tidak boleh dijadwalkan.
- Deduplikasi: telepon (dinormalisasi +62) atau email yang sama dengan lead
  atau jamaah yang ada → peringatan (400 `duplicates`); pengguna dapat tetap
  menyimpan (`allow_duplicate`). Bukan blokir keras, karena satu nomor bisa
  dipakai keluarga.
- Konversi membuat data jamaah baru (nama, telepon, email, kota sebagai
  alamat) atau menautkan jamaah yang sudah ada, idempoten. Booking tetap dibuat
  di halaman Booking (prefill `?pilgrim=` dan `?departure=`), sehingga aturan
  kursi, harga kamar dan kuota trial tidak diduplikasi.
- Izin `leads.manage`: Owner, Admin (migrasi `tenants.0011` untuk role default
  yang belum diubah), Sales. Konversi juga mensyaratkan `pilgrims.write`.
  Pemilik lead harus anggota aktif yang memiliki `leads.manage`.
- Lead tidak menyentuh SaaS Wallet (tidak billable).
- Ringkasan: hitungan per tahap, konversi = jadi ÷ (jadi + tidak jadi),
  follow-up terlambat/hari ini, sumber beserta jumlah yang jadi.

## Di luar cakupan

Atribusi agen & portal agen (P1), kampanye/broadcast, impor CSV, pengingat
follow-up otomatis lewat notifikasi, laporan funnel per periode.
