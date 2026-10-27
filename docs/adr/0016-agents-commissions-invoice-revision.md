# ADR-0016 — Agen & komisi, invoice otomatis, diskon dan revisi invoice

Tanggal: 27 Oktober 2026. Status: accepted. Menutup gap P0 G1, G4, G5 dan
sebagian G8 di [audit P0](../development/P0_GAP_AUDIT.md): PRD MOD-07,
MOD-09 (INV-01, INV-03), MOD-10, MOD-13; UAT-09/UAT-10.

## Keputusan

- **Invoice otomatis (INV-01).** Transisi booking ke RESERVED langsung
  menerbitkan invoice dalam savepoint di transaksi yang sama. Kegagalan
  (mis. konfigurasi pajak yang belum didukung) tidak membatalkan reservasi
  kursi: dicatat `invoice.auto_issue_failed` di audit, dan tombol
  "Terbitkan invoice" tetap ada sebagai jalur cadangan (idempoten).
- **Pembayar & penyesuaian harga (MOD-07).** `Booking.payer_name` menjadi
  nama pelanggan invoice. Diskon dan biaya tambahan disimpan per peserta di
  snapshot harga (`discount_idr`, `extra_idr`, `adjustment_note`); baris harga
  booking memuat paket (gross) plus baris `adjustment`. Alasan wajib, harga
  bersih minimal Rp1 (agar DP dapat dialokasikan), dan mengubah diskon butuh
  izin baru `bookings.discount` (Owner/Admin). Penyesuaian terbawa saat kamar
  atau keberangkatan draf diganti.
- **Revisi berversi (INV-03).** `POST /invoices/{id}/revise` (izin
  `invoices.issue`) hanya untuk invoice tanpa pembayaran DRAFT/SUBMITTED/
  VERIFIED. Versi lama (snapshot, PDF, checksum) disimpan immutable di
  `TravelInvoiceRevision`; nomor invoice tetap, `version` naik, alasan wajib
  dan tercetak. Credit note untuk invoice yang sudah dibayar sebagian
  ditunda ke modul refund/reschedule (P1).
- **Agen (MOD-10).** Master agen per environment; nomor rekening hanya
  disimpan termask. Booking ↔ agen dengan histori (`BookingAgentChange`);
  setelah draf, perubahan agen wajib alasan dan ditolak bila komisi sudah
  disetujui/dibayar.
- **Kebijakan komisi.** Nominal per jamaah atau persentase harga bersih,
  syarat layak "DP terverifikasi" atau "lunas", per agen/paket/periode.
  Kebijakan paling spesifik (agen+paket > agen > paket > umum) disnapshot ke
  komisi saat booking direservasi; perubahan kebijakan tidak mengubah komisi
  lama. Tanpa kebijakan yang cocok, tidak ada komisi.
- **Siklus komisi.** ESTIMATED → ELIGIBLE (otomatis saat syarat terpenuhi,
  mundur bila pembayaran direversal) → APPROVED (`commissions.approve`) →
  PAID (`commissions.pay`, membuat pengeluaran kategori "Komisi agen" pada
  rekening/tunai yang dipilih). REVERSED otomatis saat booking batal/kedaluwarsa
  atau agen diganti; pembatalan manual setelah dibayar juga membatalkan
  pengeluaran (dana kembali dari agen) dan tidak dibuat ulang otomatis.
  Komisi yang sudah dibayar pada booking yang kemudian batal diberi catatan
  review, tidak dibatalkan otomatis.
- **Laporan (MOD-13).** Tiga laporan baru dengan cek rekonsiliasi:
  Booking & Penjualan (gross/diskon/tambahan/net per paket dan agen, filter
  agen), Pembayaran (per rekening dan per petugas verifikasi, filter
  rekening), Komisi Agen (estimasi/earned/disetujui/dibayar per agen).
- **Izin default** (migrasi `tenants.0012`, hanya role default yang belum
  diubah): Admin `bookings.discount`, `agents.read/manage`,
  `commissions.read`; Sales `agents.read`; Finance `agents.read`,
  `commissions.read/policies/approve/pay`.

## Konsekuensi

- Semua tabel baru ber-RLS ENABLE+FORCE.
- Tes lama yang mengandalkan penerbitan invoice manual setelah reservasi
  disesuaikan: peserta langsung berstatus "Menunggu DP" setelah reservasi.
