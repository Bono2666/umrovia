# ADR-0007 — Harga kamar, invoice dan pembayaran travel S11

Tanggal: 26 Oktober 2026. Status: accepted untuk implementasi lokal S11.
Rujukan: Product Spec §5.2–§5.3, §6.2–§6.4, §7.3, §8.3, §9.1 dan §10.2;
PRD MOD-05/MOD-07/MOD-09; Roadmap S11.

## Keputusan bisnis DP

Pengguna memilih **setiap alokasi pembayaran terverifikasi > Rp0 memenuhi
syarat DP per jamaah**. Minimum disediakan sebagai target opsional travel.
Target yang kosong atau belum tercapai tidak menghalangi pencatatan,
pengajuan, verifikasi pembayaran, penerbitan kuitansi, atau eligibility DP.

`rules_json.payments`:

```json
{
  "dp_policy": "any_positive",
  "dp_minimum_idr": 5000000,
  "maker_checker": false
}
```

`dp_minimum_idr` dapat tidak diisi/null/0. Eligibility memakai agregat
alokasi berstatus VERIFIED untuk setiap participant. Pembayaran kelompok
yang dialokasikan ke satu peserta hanya membuat peserta itu eligible.
DP, cicilan dan pelunasan yang benar-benar diterima dihitung dalam agregat.

## Harga paket dan booking

- `PackageRoomPrice` menyimpan QUAD/TRIPLE/DOUBLE/SINGLE beserta integer
  rupiah per jamaah. Tipe yang dikosongkan pada UI tidak ditawarkan.
- Satu harga standar tetap didukung untuk paket tanpa varian. Ketika varian
  tersedia, pilihan tipe kamar wajib untuk setiap peserta. `price_idr` paket
  menampilkan harga varian terendah sebagai harga mulai.
- API booking mempertahankan daftar UUID `participants` dan menambahkan
  `room_types: {pilgrim_uuid: room_type}`. Referensi di luar daftar peserta
  atau tipe yang tidak ditawarkan ditolak.
- Snapshot per peserta memuat paket, tipe kamar, harga dan waktu. Baris
  harga booking dikelompokkan menurut snapshot, sehingga total campuran
  Quad/Triple/Double tepat. Mengubah tarif paket tidak mengubah snapshot
  peserta lama, booking RESERVED+, atau invoice terbit.
- PATCH draft mempertahankan UUID peserta yang masih sama. Peserta baru,
  perubahan tipe kamar, atau pindah keberangkatan mengambil snapshot baru;
  peserta yang tidak berubah mempertahankan harganya.

## Invoice dan PDF

- Satu invoice per booking yang telah direservasi. Lock booking dan
  constraint one-to-one membuat penerbitan ulang mengembalikan dokumen
  yang sama. Nomor INV/KWT berurutan per tenant/environment/tahun;
  demo memiliki prefix DEMO.
- Invoice line terhubung ke participant; jumlahnya harus cocok dengan
  snapshot dan baris harga booking. Nama penanggung jawab dapat diisi saat
  penerbitan; default memakai jamaah pertama. Snapshot issuer memakai
  identitas legal travel, bukan identitas platform.
- Jatuh tempo mengikuti input tanggal atau `invoice_config_json.due_days`
  (0–365, default 7). Catatan `notes` ikut disimpan. Tanggal kalender dan
  penomoran mengikuti zona waktu tenant.
- PDF dibuat lokal dengan ReportLab, tanpa mengambil aset/URL eksternal.
  PDF bytes, SHA-256, serta snapshot disimpan dalam transaksi database;
  penyimpanan tersebut menghindari file yatim ketika transaksi dibatalkan.
  PDF tetap sama setelah pembayaran atau perubahan tarif/branding.
- Dokumen berisi status pembayaran **saat terbit**; saldo terkini tersedia
  pada API/halaman Invoice. Kuitansi merekam waktu penerimaan dan verifikasi.
- Unduhan PDF melewati sesi dan RBAC tenant; respons private/no-store.
  Tidak ada URL file publik. Model guard menolak perubahan snapshot dan
  hard delete invoice/kuitansi/baris invoice. SQL administratif berada di
  luar proteksi alur aplikasi.
- Pajak/diskon otomatis belum diimplementasikan. Konfigurasi nonzero yang
  mencoba mengaktifkannya ditolak saat issue invoice agar tidak diabaikan
  dalam perhitungan total.

## Transaksi pembayaran

- `DRAFT → SUBMITTED → VERIFIED/REJECTED`; VERIFIED dapat menuju REVERSED
  dengan alasan dan persetujuan petugas berbeda dari verifikator.
- Pencatatan memerlukan alokasi eksplisit dengan jumlah tepat sama dengan
  nominal pembayaran. Kelebihan per peserta ditolak; tidak ada alokasi atau
  kredit ke invoice lain secara diam-diam. DRAFT/SUBMITTED ikut menahan
  kapasitas alokasi sampai ditolak atau diverifikasi.
- Transfer wajib memilih rekening aktif tenant. Pengajuan wajib memiliki
  referensi dana atau referensi bukti. Draf dapat melengkapi bukti sebelum
  diajukan; nominal tidak diedit setelah pencatatan.
- Urutan lock: booking → payment/invoice → participant → tenant/sequence.
  Pembayaran yang berbeda pada booking sama terserialisasi. Uji race
  memeriksa konkurensi aktual melalui koneksi PostgreSQL terpisah.
- Record/submit/verify/reject/reverse memakai `Idempotency-Key` serta hash
  payload+target. Key yang digunakan untuk isi berbeda menghasilkan 409.
  Kunci, respons, verifikasi, saldo dan kuitansi commit bersama.
- Satu payment hanya mempunyai satu kuitansi (`OneToOneField`). Retry
  verifikasi tidak menduplikasi kuitansi, audit, atau event outbox.
- `balance_idr = total_idr - sum(VERIFIED allocations)`. Reversal
  mempertahankan alokasi/PDF, menandai kuitansi REVERSED, mengembalikan saldo
  tagihan dan mengirim kasus peserta yang perlu ditinjau ke REVIEW_REQUIRED.
  Peserta yang sudah berangkat/selesai tidak diturunkan status perjalanannya.
- Pembatalan booking sebelum ada VERIFIED payment menandai invoice VOIDED;
  pembayaran terverifikasi tetap disimpan untuk review refund terpisah.

## Pemisahan travel dan SaaS

- Produksi: DP tetap VERIFIED dan kuitansi tetap terbit; participant eligible
  berada pada `DP_VERIFIED_PENDING_CHARGE` dengan `pending_charge` sampai
  implementasi wallet/charge S12–S13 menyelesaikannya. Konfirmasi baru tidak
  memakai shortcut tanpa pembayaran. Status peserta lama yang sudah aktif
  atau berangkat dipertahankan.
- Demo: flag simulasi wajib, receipt/PDF diberi DEMO, participant eligible
  dapat dikonfirmasi tanpa ledger produksi. Produksi menolak simulasi.
- `PaymentEvent` adalah outbox durable untuk payment.verified/reversed.
  Konsumen charge exactly-once, retry saldo dan notifikasi menyusul S12–S16.
  S11 tidak mengklaim debit wallet, saldo wallet, atau gateway sudah tersedia.

## Akses dan migrasi

- Admin/Finance dapat membaca dan menerbitkan invoice. Owner/Finance dapat
  memverifikasi dana dan melakukan reversal. Admin tidak mendapat
  `payments.verify`; Sales hanya membaca pembayaran yang dibuatnya sendiri.
- `maker_checker` opsional melarang pencatat memverifikasi pembayaran sendiri.
  Reversal selalu menuntut petugas berbeda dari verifikator pembayaran.
- `tenants/0006` hanya memperbarui role yang persis cocok dengan baseline
  default S10. Role kustom dan Owner tidak ditimpa. Migrasi idempoten;
  rollback tidak menghapus grant yang sudah diberikan.
- Sembilan tabel bisnis baru mempunyai RLS ENABLE+FORCE sejak migrasi
  awalnya, termasuk sequence dan idempotency/outbox. Semua operasi memakai
  scope ORM tenant serta guard environment. Referensi antar-invoice,
  participant, rekening dan tenant ditolak server-side.

## API utama

| Metode | Endpoint `/api/v1` | Akses |
|---|---|---|
| GET | `/invoices`, `/invoices/{id}` | `invoices.read` |
| GET | `/invoices/candidates` | `invoices.issue` |
| POST | `/bookings/{id}/issue-invoice` | `invoices.issue` |
| GET | `/invoices/{id}/pdf` | `invoices.read` |
| GET/POST | `/payments` | `payments.read` / `payments.create` |
| GET/PATCH | `/payments/{id}` | read scoped / create scoped, bukti DRAFT |
| POST | `/payments/{id}/submit` | create scoped |
| POST | `/payments/{id}/verify`, `/reject` | `payments.verify` |
| POST | `/payments/{id}/reverse` | `payments.reverse` + actor berbeda |
| GET | `/receipts/{id}/pdf` | `receipts.read` + cakupan payment |
| GET | `/payments/options` | `payments.create`, rekening masked |
| GET/PATCH | `/payments/settings` | `invoices.read` / `tenant.settings.write` |

Request record contoh:

```json
{
  "invoice": "invoice-uuid",
  "amount_idr": 1000000,
  "kind": "DP",
  "method": "CASH",
  "received_at": "2026-10-25T02:00:00Z",
  "reference": "Penerimaan kas 001",
  "simulate": true,
  "allocations": [{"booking_participant_id": "participant-uuid", "amount_idr": 1000000}]
}
```

Header `Idempotency-Key` wajib pada endpoint pembayaran yang mengubah state.
Verifikasi menerima `verification_note` dan dapat memeriksa ulang alokasi,
waktu penerimaan, serta bukti; isinya harus cocok dengan pencatatan.

## Kelanjutan

Wallet/top-up/debit dan kompensasi charge → S12/S13. Gateway eksternal,
unggah/scan bukti nyata, URL bertenggat dan portal → S14+. Pengiriman
notifikasi/PDF asynchronous → S16. Credit note, perhitungan pajak/diskon,
invoice per peserta dan koreksi invoice versi lanjut memerlukan tahap
lanjutan; invoice S11 memakai harga snapshot paket/kamar.
