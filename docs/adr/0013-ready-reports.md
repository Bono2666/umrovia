# ADR-0013 — Laporan siap pakai dan register pengeluaran travel

Tanggal: 27 Oktober 2026. Status: accepted. Sprint S17 (Roadmap §3: "Ready
reports: operational, finance, usage"; gate "Reconciliation vs primary
records"). PRD §51.5 FT-05 (RPT-01…06), Product Spec §8.5, §12, UI-15/16,
RPT01/RPT02.

## Keputusan

### Dihitung langsung dari catatan sumber

`GET /api/v1/reports/{operational|finance|saas}` menghitung setiap angka dari
tabel transaksi pada saat diminta dan mengembalikan `as_of`. Tidak ada tabel
agregat atau cache yang bisa basi atau berbeda dari sumber. Payload yang sama
dipakai layar dan ekspor (`?file=pdf|xlsx|csv`), sehingga filter layar dan
berkas selalu konsisten. Setiap ekspor tercatat di audit `reports.exported`.

Struktur: `kpis`, `sections` (kolom bertipe `text|money|int|percent|date`,
baris, total), dan `checks`, yaitu rekonsiliasi terhadap catatan sumber yang
ditampilkan kepada pengguna (RPT-04).

Filter: rentang tanggal lokal tenant (inklusif, maks. 2 tahun, bawaan bulan
berjalan), paket, keberangkatan, status keberangkatan (operasional). Daftar
dibatasi 500 baris dengan penanda terpotong. Cabang belum dimodelkan.

### Aturan pengakuan

| Angka | Sumber | Tanggal |
|---|---|---|
| Invoice terbit | `TravelInvoice` aktif (VOIDED dihitung terpisah) | `issue_at` |
| Pembayaran terverifikasi | `TravelPayment` VERIFIED/REVERSED | `verified_at` |
| Reversal | event `payment.reversed` | waktu event |
| Pengeluaran | `TravelExpense` tidak dibatalkan | `spent_on` |
| Piutang & aging | `balance_idr` invoice ISSUED/PARTIALLY_PAID | per `as_of`, umur dari `due_at` |
| Kas/bank | saldo awal (semua mutasi sebelum periode) + masuk − reversal − pengeluaran | per rekening, "Tunai" |
| Margin estimasi | penjualan invoice aktif − biaya tercatat per keberangkatan | keberangkatan yang berangkat atau punya invoice/biaya dalam periode |
| SaaS Wallet | `WalletLedger` (saldo awal = `balance_after` terakhir sebelum periode) | `created_at` |

Pembayaran diakui saat diverifikasi, bukan saat diterima, agar laporan periode
lampau tidak berubah ketika verifikasi terlambat. Kas/bank adalah saldo
menurut catatan Umrovia, bukan mutasi rekening bank. Margin selalu berlabel
"Estimasi" dan bukan laba rugi formal (P1, MOD-15).

### Pemisahan dana (RPT-02, POL-05)

Laporan keuangan travel tidak pernah memuat top-up, saldo atau biaya SaaS.
Laporan SaaS Wallet tidak memuat DP atau kas travel. Masing-masing memberi
catatan pemisahan dan diuji otomatis.

### Register pengeluaran travel

Spesifikasi meminta kas keluar, pengeluaran per kategori/keberangkatan dan
margin, tetapi belum ada tabelnya. `travel_finance_travelexpense` (RLS
ENABLE+FORCE): tanggal, kategori, nominal > 0, keberangkatan opsional,
rekening opsional (kosong = tunai), keterangan, referensi. Catatan tidak
diedit atau dihapus. Koreksi dilakukan dengan membatalkan (alasan wajib,
tercatat di audit) lalu mencatat ulang. Tanggal tidak boleh di masa depan.

### Akses

| Laporan | Permission | Role default |
|---|---|---|
| Operasional | `reports.read` | Owner, Admin, Finance, Operations |
| Keuangan | `reports.finance` | Owner, Finance |
| SaaS Wallet | `wallet.read` | Owner, Finance |
| Pengeluaran | `expenses.read` / `expenses.write` | Owner, Finance |

Migrasi `tenants.0009` menambah grant hanya pada role default yang belum
diubah. Laporan tidak memuat NIK/paspor; rincian piutang hanya memuat nama
pelanggan invoice.

## Di luar cakupan

Buku besar, neraca dan laba rugi formal (P1). Impor mutasi bank dan
rekonsiliasi bank. Cabang. Ekspor asinkron untuk laporan sangat besar. Laporan
platform (pendapatan platform dan funnel trial) masuk S18.
