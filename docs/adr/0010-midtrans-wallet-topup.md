# ADR-0010 — Top-up SaaS Wallet lewat Midtrans Snap

Tanggal: 26 Oktober 2026. Status: accepted. Melanjutkan ADR-0008 (transfer
manual dahulu) dan ADR-0009 (charge/pending FIFO).

## Keputusan

Pengguna memilih Midtrans sebagai payment gateway untuk **top-up SaaS Wallet**
(akun merchant milik platform). Pembayaran jamaah ke travel tidak memakai
Midtrans pada tahap ini, karena memerlukan akun dan kunci per travel.
Transfer manual tetap tersedia berdampingan.

Integrasi memakai **Snap redirect**: server membuat transaksi Snap
(`order_id = TOP-<uuid top-up>`, `gross_amount` = nominal) lalu pengguna
diarahkan ke halaman pembayaran Midtrans. Callback `finish` kembali ke
`/dashboard/wallet?topup=<id>`; halaman memeriksa status sekali. Tidak ada
script pihak ketiga di dashboard dan client key tidak diperlukan.

## Kepercayaan dan idempotensi

- Notifikasi `POST /api/v1/payments/midtrans/notification` publik (tanpa sesi
  atau CSRF) dan hanya **pemicu**. Midtrans menandatanganinya dengan Server Key
  *utama* merchant, sehingga Server Key berizin terbatas (Snap Write + Core API
  Read, yang dipakai produksi) tidak dapat memverifikasinya. Karena itu tanda
  tangan `SHA512(order_id + status_code + gross_amount + server_key)` tidak
  lagi menjadi syarat: hanya order top-up yang dikenal (`GatewayOrder`) yang
  dibaca ulang dari Status API; notifikasi tanpa tanda tangan valid untuk
  top-up yang sudah final dijawab tanpa panggilan keluar; order tak dikenal
  tidak memicu panggilan apa pun; endpoint dibatasi 120 request/menit per IP.
- Isi notifikasi **tidak** dipercaya untuk settlement: status dibaca ulang dari
  Status API Midtrans (`GET /v2/{order_id}/status`). `settlement`, atau
  `capture` dengan fraud `accept`, menjadi PAID. `pending`/`challenge` →
  PENDING. `deny`/`cancel`/`expire`/`failure` → REJECTED beralasan.
- Kredit hanya bila nominal Status API sama persis dengan top-up dan wallet
  aktif; selain itu top-up tetap PENDING dan audit/log alert dibuat.
- Satu jalur kredit untuk manual dan gateway (`_mark_paid`): ledger TOPUP unik
  per top-up, status PAID, outbox, lalu retry charge tertunda (ADR-0009).
  Notifikasi ganda/serentak tidak menambah kredit. `provider_txn_id` =
  `transaction_id` Midtrans, unik per provider.
- Refund/chargeback setelah PAID tidak mendebit otomatis; dicatat untuk
  ditinjau billing. Settlement yang datang setelah top-up REJECTED/EXPIRED
  juga hanya menjadi alert.
- Respons non-2xx (tanpa `order_id` 400, Midtrans tak terjangkau 502)
  membuat Midtrans mengulang notifikasi. Order tak dikenal (mis. notifikasi
  uji dashboard) dijawab 200.

## Transaksi, lock dan RLS

Setiap request API dibungkus satu transaksi oleh middleware tenant. Panggilan
jaringan tidak dilakukan selama lock wallet/top-up dipegang: transaksi Snap
dibuat sebelum lock; Status API dibaca sebelum `apply_gateway_status`
mengunci wallet → top-up. Webhook tidak membawa tenant, sedangkan tabel wallet
ber-RLS, sehingga tabel platform `wallet_gatewayorder` (order → tenant,
top-up; tanpa data pembayar, append-only) dipakai untuk masuk ke konteks tenant
yang benar.

PAID dari Midtrans tidak memerlukan `settled_by` (diverifikasi gateway);
top-up manual tetap wajib petugas platform berbeda dari pemohon (constraint
database). Top-up Midtrans tidak menerima bukti transfer dan tidak dapat di-
settle manual.

## Operasional

- Konfigurasi: `MIDTRANS_SERVER_KEY` (kosong = metode online nonaktif) dan
  `MIDTRANS_IS_PRODUCTION` (default sandbox). `TENANT_APP_URL` menentukan URL
  finish. Kunci hanya di environment/.env, tidak pernah di-log.
- URL notifikasi di dashboard Midtrans:
  `<PUBLIC_API_URL>/api/v1/payments/midtrans/notification` (harus dapat
  diakses publik; untuk lokal gunakan tunnel atau tombol "Periksa status").
- `POST /wallet/topups/{id}/refresh` membaca ulang status (idempoten).
  `manage.py reconcile_wallets` menyinkronkan top-up Midtrans terbuka yang
  berumur >15 menit sebelum rekonsiliasi; order tanpa transaksi ditutup
  EXPIRED satu jam setelah batas 24 jam. Kedaluwarsa otomatis berbasis waktu
  hanya untuk top-up manual.

## Di luar cakupan

Pembayaran jamaah ke travel via Midtrans (butuh kunci per travel), Snap popup
(snap.js), refund otomatis lewat API Midtrans, dan biaya transaksi gateway
(MDR) yang dibebankan ke travel — menunggu keputusan bisnis.
