# ADR-0009 — Charge SaaS dari DP terverifikasi, pending FIFO dan refund kompensasi

Tanggal: 26 Oktober 2026. Status: accepted.

## Konteks

Roadmap S13: billing event flow, insufficient wallet, refunds; gate
"exactly-once charge + ledger consistency" dan milestone M4 ("DP verified →
wallet charge precisely once with reconciliation"). S11 menyediakan verifikasi
DP dan eligibility per peserta; S12 menyediakan wallet, ledger append-only dan
primitive debit. Product Spec POL-02..POL-06, §5.3, §6.1, §7.3–§7.5, §9.2–§9.3.

## Keputusan

**Unit dan tarif.** Satu `BookingParticipant` produksi = satu charge `initial`
(`billing.SaaSCharge`). Tarif disalin dari `SaaSPriceVersion` (platform, tidak
diedit; versi baru = baris baru) saat charge dibuat. Seed `STD-2026` Rp50.000.
Bila tabel tarif kosong, layanan memulihkan versi standar POL-02 alih-alih
menggagalkan verifikasi DP. Demo tidak pernah membuat charge.

**Alur verifikasi.** `verify_payment` produksi mengunci wallet *sebelum*
booking, menandai eligibility (S11), membuat charge PENDING untuk setiap
peserta `pending_charge`, lalu memproses antrean FIFO dalam transaksi yang
sama. Saldo cukup → ledger DEBIT (`reference_id` = UUID charge), charge POSTED,
peserta `charged` dan `CONFIRMED`, outbox `saas.charge.posted`. Saldo kurang
atau wallet/tenant tidak aktif → DP tetap VERIFIED dan kuitansi terbit (HTTP
200), charge PENDING dengan `INSUFFICIENT_FUNDS`/`WALLET_UNAVAILABLE`, peserta
`DP_VERIFIED_PENDING_CHARGE`, outbox `saas.charge.pending` sekali per charge.
Verifikasi tidak pernah membuat wallet.

**Tepat sekali.** Partial unique index `uq_saas_charge_once`
(tenant, participant) untuk charge `initial` selain VOID; ledger unik per
`(wallet, kind, reference)`; serialisasi lewat lock wallet + booking. Cicilan
atau pembayaran berikutnya tidak membuat charge baru. Reversal DP atau
pembatalan booking hanya mem-VOID charge PENDING; eligibility baru kemudian
membuka epoch charge baru. Charge POSTED tidak pernah dibalik otomatis.

**Pending dan retry.** FIFO menurut `eligible_at`, ketat: begitu satu charge
tidak dapat diposting, sisanya menunggu. Retry dijalankan otomatis setelah
top-up PAID (dalam transaksi settlement, savepoint terpisah sehingga kegagalan
retry tidak membatalkan kredit bank), setelah refund disetujui, dari tombol
"Proses dengan saldo saat ini" (Owner/Finance, `wallet.topup`), dari
`manage.py retry_pending_charges` dan dari `reconcile_wallets` bila wallet
konsisten. Tenant ACTIVE ↔ RESTRICTED mengikuti ada/tidaknya charge PENDING;
RESTRICTED tidak memblokir pengguna atau top-up, hanya konfirmasi peserta baru.

**Urutan lock global.** wallet → booking → payment/invoice → peserta (urut id)
→ charge → tenant. Semua jalur yang menyentuh saldo mengambil wallet dahulu;
reversal/pembatalan tidak menyentuh wallet dan mengikuti urutan sisanya.
Kuitansi (penomoran mengunci tenant) diterbitkan setelah charge.

**Refund.** Tidak ada refund otomatis (§7.5, PAY09). Owner (`wallet.refund_request`,
tidak diberikan ke Finance secara default) mengajukan refund atas charge
POSTED untuk peserta CANCELED, beralasan. Staf platform aktif, email
terverifikasi, `is_staff` dan Django permission `billing.approve_adjustment`
memutuskan APPROVED/REJECTED dengan alasan; pemohon tidak dapat memutus
sendiri; Owner wildcard dan izin settlement top-up tidak cukup. APPROVED
menulis satu ledger `REFUND` positif (`reference_type=saas_adjustment`), charge
REFUNDED, peserta `reversed`. Replay keputusan identik mengembalikan hasil
sama; satu permintaan terbuka per charge. Refund dana jamaah oleh travel tetap
terpisah dari refund SaaS.

**Integritas database.** Trigger: terms charge/adjustment immutable, transisi
valid (PENDING→POSTED/VOID, POSTED→REFUNDED, terminal beku), POSTED harus
menunjuk DEBIT yang cocok, REFUNDED memerlukan adjustment APPROVED, APPROVED
harus menunjuk REFUND yang cocok, charge hanya untuk peserta produksi dengan
pembayaran VERIFIED pada tenant yang sama. Outbox dan tarif append-only.
`billing_saascharge`, `billing_saasadjustment`, `billing_billingevent` RLS
ENABLE + FORCE sejak migrasi pertama; tabel tarif adalah data platform.

**Rekonsiliasi.** Selain saldo/chain/top-up (S12), setiap DEBIT harus milik
tepat satu charge POSTED/REFUNDED dengan nominal sama dan setiap REFUND milik
satu adjustment APPROVED. Debit tanpa charge (`orphan_debits`) dianggap
mismatch. Jumlah charge PENDING dicatat di snapshot.

## API

Tenant: `GET /wallet` (tambahan `pending_charge_count/idr`, `posted_charge_count`,
`tenant_state`), `GET /wallet/charges?status=`, `POST /wallet/charges/retry`,
`POST /wallet/charges/{id}/refund-request`, `GET /payments/{id}/charge-preview`
(`payments.verify`; saldo hanya untuk role dengan `wallet.read`). Respons
pembayaran menyertakan `saas_charge_status` (`POSTED`,
`PENDING_INSUFFICIENT_FUNDS`, `PENDING_WALLET_UNAVAILABLE`, `REFUNDED`) dan
`unit_fee_idr` per peserta. Ledger menerima filter `kind=REFUND`.

Platform: `GET /platform/tenants/{tenant_id}/wallet/refunds?status=` (tanpa
nama jamaah) dan `POST /platform/tenants/{tenant_id}/wallet/refunds/{id}/decide`.

## Di luar cakupan

Waiver charge, kebijakan tarif/volume tier, chargeback gateway dan
platform console UI untuk refund (API tersedia) → S18 atau setelah keputusan
bisnis. Pengiriman notifikasi outbox billing → S16. Penjadwalan
`retry_pending_charges`/`reconcile_wallets` mengikuti orkestrasi job S16.
