# Audit kelengkapan fitur P0 (MVP)

Tanggal: 27 Oktober 2026. Rujukan: PRD v3.5 §5–§6 (MOD-01…MOD-13, MOD-17/18
bagian P0), §51 FT-01…FT-05 (normatif, mengungguli klasifikasi lama), §52
FT-06; Product Spec v1.2. Metode: setiap kebutuhan dicocokkan dengan model,
endpoint, halaman dan test di repositori (`main` @ 865b9a7).

Legenda: ✅ ada · 🟡 sebagian · ❌ belum ada.

## Sudah memenuhi (ringkas)

Trial 30 hari & demo terisolasi (FT-06), autentikasi & RBAC & RLS, master
jamaah (PII terenkripsi, deduplikasi), paket + harga per kamar, keberangkatan &
kursi atomik, booking & status, dokumen & checklist & review, invoice/kuitansi
otomatis sekali (FT-01 kecuali INV-01 di bawah), pembayaran DP/cicilan/
pelunasan + maker-checker + reversal, SaaS Wallet & charge Rp50.000 (OPS-02),
portal jamaah (FT-02 kecuali POR-05/06), manifest + ekspor + cetak (FT-03,
MOD-12), notifikasi email/portal + retry (FT-04), laporan operasional/keuangan/
SaaS (FT-05), pengeluaran & kas/bank per rekening, konsol platform.

## Belum / sebagian (P0)

| # | Kebutuhan PRD | Status | Temuan awal di kode (sebelum ditutup) |
|---|---|---|---|
| G1 ✅ A | **MOD-10 Agen, referral & komisi** (master agen, booking ↔ agen + histori, kebijakan komisi tersnapshot, siklus ESTIMATED→ELIGIBLE→APPROVED→PAID/REVERSED) | ✅ | Tidak ada model/endpoint/halaman agen; grant `leads.manage` saja. Laporan komisi (MOD-13) ikut belum ada. |
| G2 ✅ B | **MOD-03 Cabang/unit kerja** (kode, penanggung jawab; transaksi & laporan per cabang; penomoran per cabang/periode) | ✅ | Tidak ada model cabang (`TenantMembership` hanya catatan "branch_id menyusul"); filter cabang di laporan belum ada. Cakupan izin per cabang = TBD-08 di Spec. |
| G3 ✅ B | **MOD-02 Dashboard KPI** (jamaah, pendaftaran baru, booking per status, keberangkatan terdekat, kursi tersedia, tagihan belum lunas, pembayaran masuk, estimasi penjualan; pengingat dokumen/jatuh tempo/kursi hampir habis; grafik bulanan; drill-down) | ✅ | Halaman Ringkasan berisi checklist onboarding & beberapa ubin pengaturan; KPI operasional/keuangan baru ada di menu Laporan. |
| G4 ✅ A | **INV-01 invoice otomatis** saat booking sah disimpan | ✅ | Invoice diterbitkan manual lewat tombol "Terbitkan invoice" (idempoten). |
| G5 ✅ A | **MOD-07/09 diskon & penyesuaian harga per booking, pembayar (payer); INV-03 koreksi lewat void/credit note/revisi berversi** | ✅ | Pajak/diskon otomatis ditolak (`invoice_config`); invoice hanya bisa VOID saat booking batal, tanpa revisi/credit note. |
| G6 ✅ B | **MOD-11 saldo awal rekening + koreksi berotorisasi, transfer antarrekening berpasangan, maker-checker & lampiran bukti pengeluaran** | ✅ | Pengeluaran ada (catat/batal); saldo awal dihitung dari transaksi; tidak ada transfer antarrekening, saldo awal manual, maupun persetujuan pengeluaran. |
| G7 ✅ B | **MOD-06 daftar tunggu** saat keberangkatan penuh | ✅ | Reservasi saat penuh ditolak; tidak ada waitlist. (Hold reservation = P1.) |
| G8 🟡 A | **MOD-13 laporan Booking, Jamaah, Penjualan (gross/diskon/net), Pembayaran (per rekening/petugas), Komisi** | 🟡 | Tersedia: operasional, keuangan (penerimaan, piutang/aging, kas/bank, pengeluaran, margin), SaaS. Belum: booking, jamaah, penjualan, pembayaran per petugas, komisi. |
| G9 | **AUTH-02/03/05**: timeout sesi & logout semua perangkat; admin menonaktifkan pengguna & memicu reset sandi; audit login sukses/gagal | 🟡 | Logout & hapus membership ada; `SESSION_COOKIE_AGE` bawaan (2 minggu); login hanya dicatat di log aplikasi, tidak di audit; tidak ada logout semua perangkat/reset oleh admin. |
| G10 | **POR-05 pengumuman travel; POR-06 permintaan perubahan identitas** diverifikasi admin | ❌ | Portal hanya mengizinkan ubah kontak; tidak ada alur permintaan perubahan maupun pengumuman. |
| G11 | **MOD-04 pengelompokan keluarga, histori keberangkatan jamaah, ekspor jamaah terotorisasi** | 🟡 | Booking grup ada; tidak ada grup keluarga eksplisit, tab histori, maupun ekspor daftar jamaah. |
| G12 | **MOD-05 varian harga dewasa/anak/bayi, layanan tambahan, biaya estimasi paket** | 🟡 | Harga dasar + per tipe kamar; belum ada varian usia/add-on/biaya estimasi. |
| G13 | **MOD-08 metadata dokumen valid_from/expires_at; pemindai antimalware** | 🟡 | Kedaluwarsa paspor ada di profil; metadata per berkas belum; antimalware = butir infrastruktur di GO_LIVE_CHECKLIST. |

## Progres penutupan

- **Tahap A (penjualan & keuangan) — selesai:** G1, G4, G5 dan laporan
  Booking/Penjualan, Pembayaran, Komisi dari G8 ([ADR-0016](../adr/0016-agents-commissions-invoice-revision.md)).
  Laporan Jamaah (G8) menyusul bersama G11 di Tahap C; filter cabang bersama G2.
- **Tahap B (operasional) — selesai:** G2 cabang (master, cabang default staf,
  booking/pengeluaran/transfer bercabang, filter laporan), G3 dashboard KPI
  (indikator, pengingat, keberangkatan terdekat, grafik 12 bulan, drill-down),
  G6 kas/bank (saldo awal berotorisasi, transfer berpasangan, maker-checker &
  lampiran pengeluaran, buku kas), G7 daftar tunggu ([ADR-0017](../adr/0017-operations-cash-branches-waitlist.md)).
  Penomoran dokumen per cabang dan cakupan izin per cabang tetap TBD-08.
- **Tahap C (portal & data):** G9, G10, G11, G12, G13.

## Catatan

- P1/P2 (rooming, visa, tiket, akuntansi formal, refund/reschedule, portal
  agen, WhatsApp, multi-currency) tidak termasuk audit ini.
- Butir infrastruktur/bisnis (domain, monitoring, backup terjadwal, dsb.)
  tetap di [GO_LIVE_CHECKLIST](../release/GO_LIVE_CHECKLIST.md).
