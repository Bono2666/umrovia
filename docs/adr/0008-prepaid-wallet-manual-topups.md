# ADR-0008 — Prepaid SaaS wallet dan top-up manual

Tanggal: 26 Oktober 2026. Status: accepted.

## Keputusan

S12 mengikuti Roadmap §3: prepaid wallet, top-ups, immutable ledger;
exit gate berupa rekonsiliasi dan debit atomik. Pengguna memilih **transfer
manual dahulu** pada 26 Oktober 2026. Gateway live bukan prasyarat jalur ini.
Pemrosesan event DP, snapshot tarif charge, retry FIFO dan kompensasi tetap S13.

Wallet IDR unik per tenant dan hanya menerima transaksi produksi. Demo
mengembalikan pratinjau nol tanpa membuat wallet atau ledger. Saldo SaaS tidak
digabung dengan invoice, rekening bank travel, pembayaran DP atau kas travel.
Tarif standar yang ditampilkan Rp50.000 per booking-jamaah; kapasitas saldo
adalah estimasi `floor(balance/50000)`, bukan konfirmasi peserta.

Tidak ada minimum top-up yang disahkan. Nominal integer positif sampai Rp10
miliar diterima. Saldo maksimum Rp9 kuadriliun menjaga nilai tetap integer
presisi pada PostgreSQL dan JavaScript. Tidak ada fee/pajak implisit.

## Transfer manual dan otorisasi

Instruksi berasal dari rekening **platform**, melalui
`WALLET_MANUAL_BANK_NAME`, `WALLET_MANUAL_ACCOUNT_NAME`, dan
`WALLET_MANUAL_ACCOUNT_NUMBER`. Ketiganya wajib tersedia sebelum permintaan
baru diizinkan; tidak ada rekening contoh pada konfigurasi aplikasi.
Instruksi rekening disalin saat permintaan dibuat agar perubahan konfigurasi
tidak mengubah instruksi yang sudah diberikan.

`CREATED → PENDING → PAID/REJECTED`. CREATED tanpa bukti dapat menjadi EXPIRED
setelah 24 jam. Bukti PENDING tidak kedaluwarsa otomatis karena dana dapat
sedang ditransfer. Settlement setelah batas instruksi tetap dimungkinkan untuk
PENDING setelah pemeriksaan dana nyata. Untuk instruksi yang telah EXPIRED,
hubungi platform dan buat permintaan baru dengan jejak transfer sebelumnya;
tidak ada penghapusan riwayat lama.

Owner/Finance dapat membuat permintaan dan mengajukan referensi + lokasi bukti.
Pengajuan bukti tidak menambah saldo. Verifikasi dilakukan staf platform aktif,
email terverifikasi, `is_staff=True`, dan permission Django
`wallet.settle_topup`. Wildcard Owner tenant tidak memberikan hak platform.
Pemohon tidak boleh menyelesaikan top-up sendiri. Nominal harus cocok persis;
referensi settlement bank wajib dan unik secara global pada provider manual.
Petugas wajib mencocokkan transfer dengan mutasi bank sebelum memilih PAID.
Penolakan wajib beralasan. Evidence hanya referensi; upload/scan file menyusul.

Wallet FROZEN atau tenant SUSPENDED/TERMINATED tidak menerima perubahan.
Tenant RESTRICTED tetap dapat top-up untuk memulihkan kapasitas saldo.
Custom role tidak diberi hak tambahan secara diam-diam: migrasi hanya
meng-upgrade default Finance S11 yang persis sesuai baseline historis.

## Atomisitas dan integritas

Semua mutasi mengunci wallet sebelum top-up atau ledger. Provisioning wallet
pertama mengunci tenant, kemudian wallet. Rekonsiliasi/expiry memakai urutan
wallet → top-up yang sama. Tidak ada panggilan jaringan di transaksi finansial.

Pembuatan top-up wajib Idempotency-Key per tenant; hash request mengikat
nominal. Retry identik mengembalikan ID yang sama, perubahan nominal → 409.
Submit dan settlement idempoten berdasarkan top-up + rincian yang sama.
Settlement PAID menulis kredit, cache saldo, version, status top-up dan outbox
`wallet.topup.paid` dalam satu transaksi. Kegagalan salah satu langkah me-rollback
seluruhnya. Event tidak langsung mengonfirmasi booking pada S12.

Ledger berurutan per wallet, unik `(wallet,kind,reference_type,reference_id)`,
menyimpan nominal signed dan saldo sesudah. TOPUP positif; DEBIT negatif.
Debit internal memakai UUID charge sebagai reference, menolak penggunaan ulang
dengan rincian berbeda, dan tidak menulis apa pun jika saldo kurang. Tidak ada
endpoint tenant untuk debit bebas. S13 bertanggung jawab atas eligibility,
tarif, charge record, konsumsi event dan konfirmasi peserta.

Ledger, operasi idempotensi, outbox dan rekonsiliasi append-only pada model
**dan trigger PostgreSQL UPDATE/DELETE**. Top-up menjaga nominal/instruksi,
bukti yang telah diajukan, status terminal dan transisi di database. Trigger
juga memeriksa parent tenant; settlement harus menunjuk kredit ledger yang
cocok. Enam tabel baru memiliki RLS ENABLE + FORCE dari migrasi pertama.
Administrator database tetap memiliki kewenangan pemeliharaan; aplikasi
tidak menyediakan jalur edit atau hapus ledger.

## Rekonsiliasi dan operasi

`manage.py reconcile_wallets [--tenant SLUG]` memeriksa SUM ledger, cache,
urutan saldo sesudah, version, dan pasangan top-up PAID/kredit. Snapshot
rekonsiliasi disimpan append-only. Mismatch menghasilkan log/audit dan exit
nonzero tanpa memperbaiki saldo secara diam-diam. Command juga meng-expire
CREATED yang jatuh tempo; PENDING tidak disentuh. Jalankan melalui scheduler
operasional harian; orkestrasi worker umum mengikuti sprint notifikasi/job.

API tenant: `GET /wallet`, `/wallet/ledger`, `/wallet/ledger/export`,
`GET/POST /wallet/topups`, `GET /wallet/topups/{id}`,
`POST /wallet/topups/{id}/submit`. Ledger/top-up dipaginasi 50 baris.
Filter ledger `from/to` adalah tanggal UTC inklusif; ekspor CSV memakai filter
yang sama, maksimal 10.000 baris, no-store, dan menetralkan formula spreadsheet.

API billing platform: `GET /platform/tenants/{tenant_id}/wallet/topups`
(opsional `status`) untuk meninjau referensi bukti; dan
`POST /platform/tenants/{tenant_id}/wallet/topups/{id}/settle` dengan
`amount_idr`, `provider_txn_id`, `decision: PAID|REJECTED`, `reason`.
Keduanya menggunakan session/CSRF. Setelah otorisasi platform, tenant dipilih
eksplisit dan context aplikasi/RLS dipulihkan sebelum keluar. Tidak ada akses
PII jamaah pada endpoint platform ini.

UI tenant: SaaS Wallet, saldo/capacity/pending, instruksi transfer, pengajuan
bukti, riwayat top-up, mutasi/filter/CSV; ringkasan saldo di dashboard.
Platform console menyeluruh tetap S18; review/settlement S12 tersedia lewat
API billing berizin. Tidak ada tombol tenant untuk mengubah status PAID.
