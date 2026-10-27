# Runbook — Playbook operasional (Spec §17)

Prinsip: ledger, kuitansi dan invoice **tidak pernah diedit**. Koreksi selalu
lewat transaksi kompensasi yang tercatat di audit.

## Biaya layanan tertunda tidak terpotong

Gejala: travel RESTRICTED, "Biaya tertunda" padahal saldo cukup.
1. Konsol → Tenant → detail: saldo & jumlah tertunda.
2. Travel klik "Proses dengan saldo saat ini" di SaaS Wallet, atau operator
   `manage.py retry_pending_charges --tenant <slug>` (juga otomatis tiap 15 menit oleh worker).
3. Bila tetap tertunda: `reconcile_wallets --tenant <slug>`; mismatch → bagian "Mismatch".

## Top-up gagal / belum masuk

- Manual: Konsol → Billing → cocokkan referensi dengan mutasi rekening
  platform → "Verifikasi dana" (petugas berbeda dari pengaju). Referensi
  mutasi unik global; nominal harus sama.
- Midtrans: cek status order di dashboard Midtrans; `reconcile_wallets`
  menyinkronkan order terbuka. Nominal berbeda ditandai, tidak dikreditkan.
- Dana masuk tapi top-up kedaluwarsa: buat top-up baru dengan nominal sama,
  verifikasi dengan referensi mutasi; catat di tiket.

## Mismatch rekonsiliasi wallet

Jangan edit saldo/ledger. Bekukan wallet bila perlu (status FROZEN — saat ini
lewat `manage.py shell` oleh operator, belum ada tombol di konsol; catat di audit/tiket),
kumpulkan `WalletReconciliation.details_json`, tentukan penyebab, koreksi
lewat refund/adjustment beraudit (dua orang). Eskalasi S1 bila ada
kemungkinan charge ganda.

## Notifikasi ganda / tidak terkirim

- Ganda: periksa Notifikasi → Riwayat (satu baris per event×penerima×kanal;
  kirim ulang manual tercatat `resend_count`). Bila provider mengirim ganda,
  tidak ada tindakan data.
- Tidak terkirim (FAILED/DEAD): perbaiki SMTP, lalu "Kirim ulang".

## Penangguhan & pengakhiran tenant

- Suspend: Konsol → Tenant → Tangguhkan (alasan ≥ 10 karakter). Travel tetap
  bisa membuka tiket Bantuan. Aktifkan kembali setelah klarifikasi.
- Pengakhiran: suspend dulu → ajukan → admin lain menyetujui. Data tidak
  dihapus; ekspor/penghapusan mengikuti kontrak & prosedur hukum (TBD-10).

## Staf platform

- Tambah: `manage.py create_platform_staff <email> --role "<peran>"`;
  staf mendaftar MFA saat login pertama.
- Kehilangan perangkat MFA: verifikasi identitas di luar kanal email, lalu
  `manage.py reset_platform_mfa <email> --reason "..."`.
- Offboarding: nonaktifkan akun (`is_active=False`) dan hapus dari grup.
