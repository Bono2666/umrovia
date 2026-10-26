# Verifikasi Sprint S13

Tanggal: 26 Oktober 2026. Status: **DONE** untuk exit gate S13 dan milestone
M4. Branch: `sprint/s13-billing-charges` (dari `feat/data-corrections`).

## Cakupan

Billing event flow (DP terverifikasi → charge SaaS), saldo kurang (pending
charge + retry FIFO), dan refund lewat kredit kompensasi yang disetujui
platform. Kebijakan, urutan lock dan API: [ADR-0009](../adr/0009-saas-charge-pending-refund.md).
Dokumen baseline PRD/Product Spec/Roadmap tidak diubah.

## Bukti pengujian

- Suite backend lengkap: **335/335 lulus, 0 gagal/error/skipped** (284 detik). S13 menambah 32 kasus
  (`test_billing.py`, `test_billing_concurrency.py`) di atas 303 kasus
  sebelumnya.
- Product Spec §16: PAY01 (Rp100k → satu charge, saldo Rp50k), PAY02
  (10 verifikasi serentak → satu charge, satu kuitansi), PAY03 (wallet nol →
  DP VERIFIED, kuitansi terbit, charge pending), PAY04 (top-up → satu kredit,
  pending terposting sekali, replay settlement aman), PAY06 (DP grup ke satu
  peserta → satu charge), PAY07 (cicilan tidak menagih lagi), PAY08 (batal
  sebelum DP → tanpa charge), PAY09 (batal setelah charge → tanpa refund
  otomatis; refund memerlukan persetujuan), PAY10 (5 charge dengan dana untuk
  2 → 2 POSTED, 3 PENDING, saldo nonnegatif), SEC03 (replay dan 5 persetujuan
  refund serentak → satu ledger REFUND).
- Race nyata top-up settlement vs tiga verifikasi DP serentak: semua 200,
  tanpa deadlock, charge tertua selalu terposting, rekonsiliasi konsisten.
  Suite konkurensi S11–S13 (14 kasus) diulang 3× tanpa kegagalan.
- FIFO ketat lintas booking; RESTRICTED ↔ ACTIVE mengikuti antrean; wallet
  dibekukan → `PENDING_WALLET_UNAVAILABLE`, kemudian `retry_pending_charges`
  dan `reconcile_wallets` memposting setelah aktif kembali.
- Reversal DP mem-VOID charge pending dan eligibility berikutnya membuka
  epoch baru; reversal setelah POSTED tidak mengubah charge maupun saldo.
- Refund: hanya charge POSTED untuk peserta CANCELED; Finance default tidak
  berwenang; Owner wildcard dan izin settlement top-up tidak dapat memutus;
  pemohon tidak dapat memutus sendiri; penolakan tanpa kredit; antrean
  platform tanpa nama jamaah.
- Guard database: UPDATE/DELETE charge, outbox dan tarif ditolak via SQL;
  transisi ilegal dan REFUNDED tanpa kredit disetujui ditolak; charge untuk
  pembayaran belum VERIFIED ditolak; charge terbuka kedua per peserta ditolak.
- RLS ENABLE+FORCE pada `billing_saascharge`, `billing_saasadjustment`,
  `billing_billingevent`; probe role non-superuser: konteks kosong/tenant lain
  0 baris, tenant benar melihat barisnya.
- Tarif hilang dari tabel tidak menggagalkan verifikasi DP (versi standar
  dipulihkan). Ditemukan lewat test transaksional yang mem-flush seed.
- Demo tidak pernah membuat charge; pratinjau biaya menyembunyikan saldo
  untuk role tanpa `wallet.read`.
- Perubahan pada test S12: debit mentah tanpa charge kini ditandai
  `orphan_debits` oleh rekonsiliasi, dan top-up PAID kini memposting charge
  pending (sebelumnya sengaja tidak). Assertion disesuaikan dengan invariant baru.
- Ruff, ESLint dan TypeScript lulus. `makemigrations --check` bersih.
- Migrasi clean → rollback (`billing zero`, `wallet 0001`) → reapply lulus
  pada database sementara; seed STD-2026, RLS dan 6 trigger terpasang.
- OpenAPI: enam path baru tergenerasi tanpa error dari endpoint S13; error
  inferensi serializer pada APIView lama tetap seperti catatan S12.

## Browser

Playwright (`playwright-core` lokal + Chrome) pada API :8013 dan Next dev
:3013 dengan database **terpisah** `umrovia_s13_ui` berisi travel fiktif.
Alur: login → Wallet menampilkan banner charge tertunda dan status
"Menunggu saldo" → Pembayaran: dialog verifikasi menampilkan biaya
1 × Rp50.000, saldo Rp0 dan antrean → verifikasi sukses dengan pesan
menunggu saldo → top-up dan bukti via UI → settlement platform berizin →
kedua charge terposting, banner hilang, saldo Rp0 → booking dibatalkan →
"Ajukan refund" dari UI → antrean platform tanpa nama jamaah → disetujui →
status Direfund, mutasi "Refund SaaS", saldo Rp50.000 → dark mode dan mobile
390px tanpa overflow horizontal. Tidak ada pageerror. Perbaikan dari QA:
label status peserta dan tata letak tombol refund.

Banner trial pada screenshot berasal dari fixture yang membuat tenant
langsung tanpa riwayat konversi, bukan perilaku S13.

## Batas S13

Waiver, tarif bertingkat/volume, dan chargeback gateway menunggu keputusan
bisnis. UI platform console untuk antrean refund → S18 (API tersedia).
Pengiriman notifikasi dari `billing_billingevent` dan penjadwalan
`retry_pending_charges`/`reconcile_wallets` → S16. Build/runtime Docker
belum dijalankan ulang untuk S13.
