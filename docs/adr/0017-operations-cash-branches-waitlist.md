# ADR-0017 — Cabang, daftar tunggu, kas & bank, dashboard KPI

Tanggal: 27 Oktober 2026. Status: accepted. Menutup gap P0 G2, G3, G6 dan G7
di [audit P0](../development/P0_GAP_AUDIT.md): PRD MOD-02, MOD-03, MOD-06, MOD-11.

## Keputusan

- **Cabang (MOD-03).** `tenants.Branch` (kode unik per travel, penanggung
  jawab, kontak, aktif). Booking, pengeluaran, transfer kas dan agen dapat
  ditandai cabang; staf punya cabang default (`TenantMembership.branch`) yang
  mengisi transaksi baru bila tidak dipilih. Laporan finance/penjualan/
  pembayaran/komisi dan buku kas dapat disaring per cabang. Cabang nonaktif
  tidak dapat dipilih tetapi riwayat tetap. **Belum**: penomoran dokumen per
  cabang dan pembatasan akses data per cabang (Spec TBD-08) — semua staf
  melihat seluruh cabang sesuai role.
- **Daftar tunggu (MOD-06).** Hanya untuk keberangkatan OPEN tanpa kursi
  tersisa; satu jamaah satu entri menunggu per keberangkatan; tidak menahan
  kursi. Diproses FIFO: posisi N hanya dapat dibuatkan booking draf bila kursi
  tersedia ≥ N. Kolom "Daftar tunggu" ditambahkan ke laporan operasional.
- **Kas & bank (MOD-11).**
  - Saldo awal per rekening atau kas tunai berlaku mulai tanggal `as_of`
    (transaksi sebelumnya dianggap tercakup). Saldo awal pertama langsung
    berlaku; koreksi wajib alasan dan menunggu persetujuan
    (`bank_accounts.approve`, default Owner), lalu menggantikan yang lama.
  - Transfer antarrekening adalah satu catatan berisi pasangan keluar/masuk;
    total kas travel tidak berubah; koreksi dengan pembatalan.
  - Maker-checker kas (pengaturan `rules_json.cash.maker_checker`): bila aktif,
    pengeluaran baru berstatus menunggu dan hanya dihitung setelah disetujui
    staf lain (`expenses.approve`, default Owner); koreksi saldo awal juga
    harus disetujui staf lain. Pengeluaran membawa penerima dana dan lampiran
    bukti (PDF/JPG/PNG, validasi magic bytes, penyimpanan privat).
  - Buku kas (`/cash/book`) dan bagian kas pada laporan keuangan memakai satu
    perhitungan bersama (`travel_finance.services.ledger`).
- **Dashboard KPI (MOD-02).** `GET /dashboard/summary` menghitung dari
  catatan sumber: jamaah, booking & penjualan bulan ini, booking per status,
  kursi tersedia, tagihan belum lunas/lewat jatuh tempo, pembayaran bulan ini,
  pengingat (kursi hampir habis, daftar tunggu siap diproses, dokumen belum
  lengkap H-30, invoice jatuh tempo, pembayaran menunggu verifikasi),
  keberangkatan terdekat dan grafik 12 bulan. Setiap blok mengikuti izin role;
  setiap angka menaut ke halaman detail.

## Konsekuensi

- Tabel baru (`tenants_branch`, `booking_waitlistentry`,
  `travel_finance_openingbalance`, `travel_finance_cashtransfer`) ber-RLS
  ENABLE+FORCE. Izin default baru via migrasi `tenants.0014` (role default
  yang belum diubah saja).
- Pengeluaran yang dicatat sebelum fitur ini dianggap sudah disetujui.
