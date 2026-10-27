# ADR-0019 — Cakupan akses per cabang (TBD-08, opsi C)

Tanggal: 27 Oktober 2026. Status: accepted (default yang dapat diatur; akan
divalidasi dengan travel pilot bercabang). Menjawab Product Spec TBD-08
"Branch-level permissions" dan melengkapi ADR-0017.

## Konteks

ADR-0017 menambahkan master cabang dan penandaan cabang pada transaksi, tetapi
semua staf masih melihat data seluruh cabang. Spec meminta pemisahan
booking/keuangan per cabang ditetapkan saat pilot.

## Keputusan (opsi C — campuran, dapat diatur per role)

- **Cakupan role** `Role.branch_scope`: `ALL` (semua cabang) atau `OWN`
  (cabang sendiri). Default: Owner, Admin, Finance = `ALL`; Sales, Operations,
  Document Reviewer = `OWN`. Owner selalu `ALL`. Hanya staf berakses semua
  cabang yang boleh memberi cakupan `ALL` ke role (anti eskalasi).
- **Penugasan staf** `MembershipBranch`: satu staf dapat ditugaskan ke
  beberapa cabang; cabang default otomatis termasuk penugasan.
- **Aturan baca** staf `OWN`: transaksi cabang yang ditugaskan **ditambah**
  transaksi tanpa cabang (pusat/data lama). Staf `OWN` tanpa penugasan hanya
  melihat transaksi tanpa cabang. Travel tanpa cabang aktif tidak terpengaruh.
- **Data yang dipisah per cabang**: lead, booking (beserta invoice, revisi,
  PDF, pembayaran, kuitansi, komisi), pengeluaran (+ lampiran & persetujuan),
  transfer kas, laporan penjualan/pembayaran/komisi/jamaah, KPI Ringkasan,
  riwayat perjalanan jamaah, roster manifest/cetak.
- **Data induk dipakai bersama**: paket, keberangkatan, jamaah (agar deteksi
  duplikat NIK tetap bekerja), agen, daftar tunggu, dokumen jamaah.
- **Aturan tulis** staf `OWN`: transaksi baru hanya ke cabang dalam cakupannya
  (default: cabang default); tidak boleh membuat transaksi pusat (tanpa cabang)
  bila sudah ditugaskan.
- **Khusus cakupan semua cabang**: buku kas & saldo awal, laporan keuangan dan
  SaaS, penerbitan manifest resmi dan PDF versi manifest (dokumen tingkat
  keberangkatan). Laporan operasional (agregat per keberangkatan, tanpa PII)
  tetap terbuka.
- **Penomoran dokumen** tetap satu urutan per travel (aman untuk faktur/pajak,
  terkait TBD-05); kode & nama cabang dicetak di invoice sebagai informasi.

## Konsekuensi

- Penyaringan diterapkan di server untuk setiap endpoint (`scope_filter`,
  `assert_branch_allowed`, `require_full_scope`), diuji dengan skenario
  kebocoran antar-cabang (`tests/test_branch_scope.py`).
- Migrasi `tenants.0016` menambah kolom cakupan (role default Sales/Operations/
  Document Reviewer → `OWN`) dan menyalin cabang default staf menjadi penugasan.
- Bila pilot memilih penomoran per cabang atau pemisahan master jamaah, keputusan
  ini direvisi lewat ADR baru.
