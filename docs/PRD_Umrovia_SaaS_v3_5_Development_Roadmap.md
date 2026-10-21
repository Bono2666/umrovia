# PRODUCT REQUIREMENTS DOCUMENT (PRD)
## Sistem Informasi Manajemen Travel Umroh & Haji — SaaS Multi-Tenant

| Metadata | Nilai |
|---|---|
| Versi dokumen | **3.5 — SaaS Pay-per-Jamaah + Free Trial** |
| Tanggal | 21 Oktober 2026 |
| Status | Draft pengembangan, perlu validasi stakeholder |
| Referensi utama | https://demov2.softwareumroh.com/ |
| Produk referensi | Amsol SIM-Umroh V2 |
| Platform yang dirancang | SaaS multi-tenant berbasis web; portal travel, platform owner, agen, dan jamaah |
| Bahasa | Indonesia |
| Mata uang | IDR (opsional multi-currency) |
| Model bisnis | **Rp50.000 per booking-jamaah setelah DP diterima dan terverifikasi; Rp0 biaya bulanan dan Rp0 setup standar; prepaid wallet (MVP)** |
| Arsitektur tenancy | Shared application + shared database dengan tenant_id dan isolasi ketat pada MVP; opsi database-per-tenant untuk enterprise |
| Status fitur SaaS | **[S] Usulan baru, bukan fitur yang terverifikasi pada aplikasi referensi** |

> **Transparansi riset:** Halaman publik situs demo terindeks sebagai aplikasi administrasi travel Haji-Umroh untuk PT Safara Layanan Utama. Akses langsung situs demo mengalami timeout; login menggunakan kredensial yang diberikan **belum berhasil diuji**. Karena itu, dokumen ini **bukan hasil audit terverifikasi atas seluruh menu internal**. Fitur dengan label **[R]** memiliki dukungan dari informasi publik resmi Amsol (dokumentasi/tutorial); fitur **[U]** merupakan usulan spesifikasi agar sistem lengkap. Struktur menu, field, tabel basis data, dan alur bisnis tetap perlu divalidasi melalui akses demo.

## 1. Ringkasan Eksekutif

Produk merupakan **Software-as-a-Service (SaaS) multi-tenant**: satu platform melayani banyak perusahaan travel yang masing-masing mempunyai ruang kerja, konfigurasi, pengguna, dan data terisolasi. Di dalam tiap tenant, sistem terpusat menangani operasional biro perjalanan Umroh dan Haji: dari perancangan paket, pemasaran melalui agen, pendaftaran jamaah, pengumpulan dokumen, penjadwalan keberangkatan, pembayaran, pelaksanaan perjalanan, hingga pelaporan keuangan dan manajemen. Target utamanya adalah mengganti proses spreadsheet dan dokumen terpisah dengan workflow yang auditable.

### 1.1 Masalah bisnis
- Data jamaah duplikat dan tersebar pada sejumlah file atau staf.
- Ketersediaan kursi, status pembayaran, dan kelengkapan dokumen sulit dipantau serentak.
- Komisi agen dan biaya perjalanan sulit direkonsiliasi.
- Pelacakan transaksi, piutang, pengeluaran, dan margin per keberangkatan masih manual.
- Dokumen operasional (manifest, rooming list, invoice) perlu direkap berulang.
- Akses data sensitif dan histori perubahan belum terdokumentasi konsisten.

### 1.2 Sasaran dan indikator keberhasilan
| Tujuan | KPI yang diukur | Target awal (hipotesis) |
|---|---|---|
| Efisiensi pendaftaran | Durasi input satu jamaah | ≤ 5 menit setelah data lengkap |
| Akurasi kursi | Perbedaan seat tersisa dan booking aktif | 0 kasus overbooking sistem |
| Kualitas dokumen | Jamaah berangkat dengan checklist wajib lengkap | 100% atau tercatat pengecualian resmi |
| Transparansi pembayaran | Transaksi terlacak sampai invoice dan kas/bank | 100% transaksi terposting |
| Akuntabilitas | Perubahan finansial penting memiliki audit log | 100% perubahan |
| Kinerja dashboard | Waktu buka dashboard standar | p95 < 3 detik (target rancangan) |

Target di atas adalah usulan, bukan klaim performa aplikasi referensi.

### 1.3 Perubahan strategis pada versi 2.0
- **Pembeli produk:** perusahaan travel/KBIH yang berlangganan, bukan satu perusahaan pemilik instalasi.
- **Operator platform:** Platform Owner mengelola tenant, paket SaaS, langganan, billing, keamanan dan support tanpa otomatis memperoleh akses ke isi data jamaah.
- **Pengguna tenant:** Owner/Admin Travel dan staf mengakses data hanya dalam perusahaan sendiri; peran agen/jamaah tidak melintasi tenant kecuali ada relasi eksplisit yang berizin.
- **Dua pembukuan yang tidak boleh dicampur:** (1) tagihan biaya pemakaian SaaS + wallet antara platform dan travel; (2) invoice serta penerimaan DP jamaah milik travel. Dana DP bukan dana milik operator SaaS.
- **Kontrak MVP:** onboarding gratis, wallet deposit, harga Rp50.000 per jamaah terkonfirmasi DP, pemotongan tepat sekali, pembatalan/refund terkontrol, isolasi data, platform console, audit, backup/restore dan ekspor data. Tidak ada subscription berulang wajib.

## 2. Fakta Referensi, Asumsi, dan Keterbatasan

### 2.1 Informasi publik yang terkonfirmasi
- Situs demo publik: https://www.demov2.softwareumroh.com/ menampilkan aplikasi manajemen administrasi travel Haji-Umroh dan pintu masuk ke sistem serta SISKOPATUH.
- Situs pengembang: https://softwareumroh.com/ dan https://softwareumroh.com/produk memasarkan Amsol SIM-Umroh sebagai software manajemen biro travel umroh.
- Dokumentasi: https://softwareumroh.com/biro-travel-umroh memuat panduan terkait **paket umroh, agen, pengguna, rekening bank pada pengaturan KBIH, serta cetak amplop KBIH**.

### 2.2 Tidak terverifikasi
- Menu lengkap dashboard setelah login, field detail, desain form, layar, jenis laporan, hak akses spesifik, integrasi aktual, endpoint API, DBMS, teknologi backend, dan metode posting keuangan.
- Apakah koneksi SISKOPATUH yang ditampilkan merupakan integrasi API atau hanya tautan keluar.
- Modul haji, tiket, visa, akuntansi dan lain-lain **tidak boleh dianggap pasti ada di versi demo** hanya karena tercantum di PRD ini.

### 2.3 Prinsip perancangan
1. Single source of truth untuk jamaah, paket, keberangkatan dan pembayaran.
2. Pemisahan antara *master data*, *transaksi*, dan *laporan*.
3. Pembukuan tidak boleh berubah tanpa jejak audit atau transaksi koreksi.
4. Akses berbasis role dan lingkup cabang.
5. Setiap langkah dengan status eksplisit, validasi, dan penanggung jawab.
6. Integrasi eksternal dibuat melalui adapter yang dapat dinonaktifkan.

## 3. Ruang Lingkup

### 3.1 Fase MVP (P0)
- Login, profil perusahaan, pengguna, role dan permission.
- Dashboard utama dengan KPI dan notifikasi dasar.
- Master jamaah dan dokumen.
- Master paket, jadwal keberangkatan, komponen layanan, kapasitas kursi.
- Booking/pendaftaran, anggota keluarga, reservasi kursi dan invoice.
- Pembayaran manual, verifikasi, kwitansi, saldo tagihan.
- Master agen, atribusi booking, komisi sederhana.
- Kas/bank dan pengeluaran dasar.
- Manifest, daftar keberangkatan, laporan penjualan dan piutang.
- Cetak dan ekspor dokumen; audit log inti.

### 3.2 Tahap lanjutan (P1)
- Operasional keberangkatan lengkap (hotel, kamar, tiket, visa, perlengkapan).
- Akuntansi double-entry dan rekonsiliasi lanjutan.
- Komisi bertingkat dan pencairan massal.
- Notifikasi WhatsApp/email, portal jamaah/agen.
- Refund, reschedule, transfer booking dan approval kompleks.
- Impor massal, integrasi pembayaran, pengelolaan banyak cabang.

### 3.3 Opsional (P2)
- CRM prospek dan kampanye marketing.
- Multi-currency dan kurs historis.
- Aplikasi mobile jamaah/tour leader.
- Integrasi SISKOPATUH melalui jalur resmi yang diizinkan.
- BI lanjutan, budgeting, fitur haji khusus, OCR paspor.

### 3.4 Di luar cakupan MVP
- Pemesanan tiket penerbangan langsung ke GDS.
- Pengajuan visa secara otomatis tanpa integrasi resmi.
- Integrasi penuh Nusuk/SISKOPATUH yang belum memiliki kontrak atau mekanisme sah.
- Pelacakan lokasi langsung dan komunikasi kelompok real-time.

## 4. Pengguna dan Hak Akses

| Role | Tanggung jawab | Lingkup akses |
|---|---|---|
| Super Admin | Konfigurasi global, keamanan, organisasi | Seluruh sistem |
| Owner/Direktur | KPI, margin, laporan, approval tertentu | Seluruh cabang sesuai kebijakan |
| Admin Operasional | Paket, booking, manifest, keberangkatan | Transaksi operasional |
| CS/Pendaftaran | Profil dan pendaftaran jamaah | Data jamaah/booking yang berwenang |
| Finance/Kasir | Tagihan, penerimaan, pengeluaran, refund | Modul keuangan |
| Akuntan | COA, jurnal, tutup buku, rekonsiliasi | Modul akuntansi |
| Dokumen/Visa | Verifikasi paspor/dokumen dan checklist | Operasional dokumen |
| Koordinator Keberangkatan | Hotel, kamar, tiket, kegiatan, manifest | Grup keberangkatan |
| Agen | Prospek/booking milik sendiri, komisi | Data sendiri |
| Jamaah (opsional) | Data pribadi, booking, tagihan, jadwal | Data sendiri |
| Auditor (opsional) | Inspeksi dan ekspor laporan | Read-only |

**RBAC:** permission CRUD + approve + export + delete + sensitive-view untuk setiap entitas. Otorisasi harus diperiksa server-side pada setiap permintaan. Cabang dan *record ownership* membatasi data. Contoh: kasir boleh membuat penerimaan tetapi tidak menyetujui pembatalan penerimaannya sendiri.

## 5. Peta Modul dan Prioritas

| Kode | Modul | Prioritas | Status referensi |
|---|---|---|---|
| MOD-01 | Autentikasi & Pengguna | P0 | [R] Pengguna disebut dalam tutorial |
| MOD-02 | Dashboard & Notifikasi | P0 | [U] |
| MOD-03 | Perusahaan, Cabang & KBIH | P0 | [R] Pengaturan KBIH/rekening bank |
| MOD-04 | Master Jamaah | P0 | [U] |
| MOD-05 | Paket Umroh/Haji | P0 | [R] Paket umroh dalam tutorial |
| MOD-06 | Keberangkatan & Kuota | P0 | [U] |
| MOD-07 | Pendaftaran/Booking | P0 | [U] |
| MOD-08 | Dokumen Jamaah | P0 | [U] |
| MOD-09 | Invoice, Pembayaran, Piutang | P0 | [U] |
| MOD-10 | Agen & Komisi | P0 | [R] Agen dalam tutorial |
| MOD-11 | Kas, Bank & Pengeluaran | P0 | [R] Rekening bank; transaksi detail [U] |
| MOD-12 | Manifest & Dokumen Cetak | P0 | [R] Cetak amplop KBIH; manifest [U] |
| MOD-13 | Laporan | P0 | [U] |
| MOD-14 | Operasional Tiket/Hotel/Visa | P1 | [U] |
| MOD-15 | Akuntansi & Jurnal | P1 | [U] |
| MOD-16 | Refund/Reschedule | P1 | [U] |
| MOD-17 | Portal Agen [P1] / Portal Jamaah [P0] | P0/P1 | [U] |
| MOD-18 | Notifikasi Inti [P0] / Integrasi Lanjutan [P1] | P0/P1 | [U] |
| MOD-19 | CRM & Lead | P2 | [U] |
| MOD-20 | Multi-currency, BI & Mobile | P2 | [U] |

## 6. Spesifikasi Kebutuhan Fungsional

### MOD-01 — Autentikasi, Pengguna, Role [P0]
**Tujuan:** akses aman dengan kontrol terperinci.

| ID | Requirement | Kriteria penerimaan |
|---|---|---|
| AUTH-01 | Login via username/email dan password | Akun aktif dapat login; kredensial salah menghasilkan pesan generik |
| AUTH-02 | Logout, timeout sesi, logout seluruh perangkat | Sesi tidak valid setelah logout/revokasi |
| AUTH-03 | Manajemen pengguna | Admin dapat tambah, nonaktif, reset sandi, menetapkan role |
| AUTH-04 | Pembatasan per role, cabang, kepemilikan | Akses URL/API tanpa izin ditolak 403 |
| AUTH-05 | Audit login, failed attempt, perubahan izin | Tersimpan actor, timestamp, IP, perubahan |
| AUTH-06 | MFA untuk admin/finance (P1) | Tindakan sensitif perlu verifikasi tambahan |

**Field pengguna:** ID, nama, username, email, telepon, cabang, role, status, last_login, created_at, updated_at. Password hanya disimpan dalam bentuk hash kuat.

### MOD-02 — Dashboard [P0]
- KPI: jumlah jamaah, pendaftaran baru, booking per status, keberangkatan terdekat, kursi tersedia, tagihan belum lunas, pembayaran masuk, estimasi penjualan.
- Filter periode, cabang, paket, keberangkatan, agen.
- Widget pengingat: dokumen tidak lengkap, jatuh tempo pembayaran, visa pending, kursi hampir habis.
- Grafik booking bulanan dan pembayaran bulanan; setiap kartu bisa drill-down ke data yang dibatasi permission.

**Acceptance:** angka sama dengan total daftar ketika filter identik; tidak mencampur data cabang lain.

### MOD-03 — Pengaturan Perusahaan/KBIH [P0]
- Profil badan usaha, nama dagang, alamat, kontak, logo, identitas legal dan izin usaha bila dibutuhkan.
- Cabang/unit kerja, kode dan penanggung jawab.
- Rekening bank perusahaan: bank, nama pemilik, nomor rekening terenkripsi/termasking sesuai role, status aktif.
- Template dokumen: invoice, kuitansi, formulir, amplop KBIH [R], syarat ketentuan, tanda tangan/stempel digital jika diizinkan.
- Penomoran dokumen terkonfigurasi per cabang dan periode; zona waktu Asia/Jakarta.

**Aturan:** nomor dokumen unik; rekening nonaktif tidak bisa dipilih untuk transaksi baru, tetapi tetap terlihat dalam histori.

### MOD-04 — Master Jamaah [P0]
**Data inti**: kode jamaah, nama sesuai dokumen, NIK (opsional sesuai proses), jenis kelamin, tanggal/tempat lahir, kewarganegaraan, status perkawinan, alamat, email, HP/WhatsApp, kontak darurat, data wali/mahram bila relevan, catatan kebutuhan khusus dengan pembatasan akses.

**Data paspor:** nomor paspor, nama paspor, tanggal terbit, tanggal kedaluwarsa, tempat terbit, kewarganegaraan. **Dokumen:** paspor, foto, KTP, KK, dan dokumen lain yang diwajibkan untuk paket tertentu.

**Fungsi:** CRUD, pencarian, deduplikasi, histori keberangkatan, pengelompokan keluarga, impor CSV/XLSX tervalidasi (P1), ekspor terotorisasi, masking data sensitif.

**Aturan:** identitas yang sama ditandai sebagai potensi duplikat, bukan otomatis digabung. Masa berlaku paspor diverifikasi terhadap aturan perjalanan yang berlaku pada tanggal keberangkatan dan kebijakan penyedia layanan, bukan angka yang di-hardcode.

### MOD-05 — Master Paket [P0]
**Entitas paket:** kode, nama, jenis layanan (Umroh/Haji/ziarah), deskripsi, durasi, fasilitas, non-fasilitas, kebijakan pembatalan, syarat pembayaran, foto/brosur, harga dasar, mata uang, status DRAFT/ACTIVE/INACTIVE/ARCHIVED.

**Varian harga:** dewasa/anak/bayi jika relevan; tipe kamar QUAD/TRIPLE/DOUBLE/SINGLE; upgrade hotel, tambahan layanan, diskon dan biaya ekstra.

**Biaya estimasi:** tiket, hotel, transportasi, visa, makan, perlengkapan, pembimbing, asuransi, pajak/biaya administrasi sesuai kebijakan.

**Aturan:** perubahan harga paket yang sudah memiliki booking tidak mengubah invoice existing kecuali melalui perubahan terotorisasi.

### MOD-06 — Jadwal Keberangkatan & Kuota [P0]
- Satu paket memiliki banyak jadwal keberangkatan dengan kode unik.
- Field: keberangkatan, kepulangan, kota asal, maskapai/rute (opsional), meeting point, kapasitas, kuota blokir, batas pendaftaran, status.
- Status: DRAFT → OPEN → FULL/CLOSED → PREPARATION → DEPARTED → COMPLETED; dapat CANCELLED dengan approval dan penanganan booking.
- Kontrol kuota atomik saat booking; daftar tunggu jika penuh; hold reservation dengan durasi konfigurasi (P1).
- Pendaftaran tidak diterima apabila tanggal sudah lewat atau keberangkatan tertutup.

**Formula kursi tersedia:** kapasitas − jumlah seat untuk booking aktif yang mengonsumsi kursi − seat blocking; pending yang sudah kedaluwarsa tidak memakan kursi.

### MOD-07 — Pendaftaran/Booking Jamaah [P0]
**Alur:** pilih paket → pilih keberangkatan/room type → pilih/buat profil jamaah → input jumlah peserta dan relasi keluarga → tentukan agen/sumber → hitung harga/discount → simpan booking → invoice → proses pembayaran.

**Field:** booking number, booking date, branch, departure_id, customer/payer, participants, agent, quantity, list price, adjustment, discount, tax/fee sesuai konfigurasi, total, due dates, notes, status.

**Status:** DRAFT → RESERVED → CONFIRMED → DOCUMENT_PROCESS → READY_TO_DEPART → DEPARTED → COMPLETED; CANCELED dan EXPIRED sebagai terminal/pengecualian yang dikontrol.

**Aturan:**
- Satu jamaah tidak boleh memiliki booking aktif ganda pada keberangkatan sama tanpa override eksplisit.
- Nilai invoice dihasilkan dari *snapshot* harga saat booking.
- Reserved hanya dikonfirmasi sesuai aturan DP/pelunasan yang dapat dikonfigurasi.
- Canceled melepas seat, membatalkan tagihan terbuka sesuai kebijakan, dan memicu review refund/komisi.
- Untuk kelompok, setiap peserta punya profil dan checklist sendiri, satu booking dapat ditagihkan bersama.

### MOD-08 — Manajemen Dokumen [P0]
- Checklist wajib per jenis paket/keberangkatan dan kategori jamaah.
- Unggah berkas dan metadata: jenis, nama, valid_from, expires_at, uploader, reviewer, review_at, status.
- Status: MISSING → UPLOADED → UNDER_REVIEW → VERIFIED atau REJECTED → UPLOADED.
- Alasan penolakan wajib; dokumen versi lama tetap tersimpan sesuai retensi.
- Validasi tipe MIME nyata, ukuran, scan antivirus, proteksi akses dan URL unduh sementara.
- Dashboard menampilkan persen kelengkapan per jamaah dan manifest.

### MOD-09 — Tagihan, Pembayaran & Piutang [P0]
- Invoice unik dari booking, dengan item per paket/layanan, due_date, total, diskon, pajak/beban sesuai konfigurasi.
- Termin pembayaran fleksibel: DP, cicilan, pelunasan; jadwal dan nominal.
- Catat pembayaran: tanggal, nominal, metode (transfer, tunai, kanal lain), rekening tujuan, nomor referensi, bukti, penerima.
- Verifikasi pembayaran oleh role berwenang, larangan self-approval jika aturan maker-checker aktif.
- Status pembayaran: UNPAID, PARTIAL, PAID, OVERDUE, VOID; status invoice dan booking adalah domain terpisah.
- Cetak kuitansi bernomor dan riwayat penerimaan.

**Formula:** `outstanding = invoice_total - verified_payments - applied_credits + reversed_payments`, dengan aturan pembulatan rupiah. Pembayaran berlebih menjadi *unapplied credit* atau ditolak sesuai kebijakan, tidak diam-diam menutup invoice lain.

### MOD-10 — Agen, Referral, Komisi [P0]
- Master agen: kode, nama, telepon, identitas bisnis, rekening, cabang/area, status, level opsional.
- Hubungkan setiap booking ke agen yang mendapat kredit penjualan dengan histori perubahan.
- Kebijakan komisi: fixed/percentage dari basis harga yang ditentukan, per produk/periode/agen; disimpan snapshot pada booking.
- Siklus komisi: ESTIMATED → ELIGIBLE → APPROVED → PAID; REVERSED bila booking batal.
- Komisi menjadi eligible setelah syarat bisnis tercapai (mis. pembayaran minimal atau lunas), bukan otomatis ketika booking dibuat.
- Portal ringkas agen untuk booking dan komisi sendiri (P1).

### MOD-11 — Kas, Bank & Biaya [P0]
- Master rekening/kas, saldo awal dan otorisasi koreksi saldo awal.
- Kas masuk berkaitan dengan pembayaran jamaah; kas keluar berupa biaya operasional, vendor, komisi, reimburse.
- Transfer antarrekening direkam sebagai pasangan transaksi terkait sehingga total saldo perusahaan tidak berubah.
- Transaksi diklasifikasi dengan kategori, departemen, cabang dan keberangkatan.
- Lampiran bukti, nomor transaksi, penerima/pembayar, tanggal efektif, maker, checker.
- Transaksi terposting tidak boleh dihapus secara permanen; koreksi memakai reversal.
- Laporan buku kas/bank, arus masuk/keluar, pengeluaran menurut kategori dan perjalanan.

### MOD-12 — Manifest & Cetak Dokumen [P0]
- Manifest keberangkatan dapat difilter menurut penerbangan, paket, grup, status dokumen/pembayaran.
- Ekspor XLSX/CSV yang tidak mengubah data dan PDF untuk cetak.
- Generator dokumen: formulir pendaftaran, invoice, kuitansi, daftar jamaah, label/amplop KBIH, rooming list (P1), daftar perlengkapan (P1).
- Dokumen berisi versi template, tanggal cetak, cabang, identitas penerbit dan nomor referensi.
- Data rahasia pada ekspor hanya muncul untuk pengguna yang berwenang dan dicatat di audit log.

### MOD-13 — Pelaporan [P0]
| Laporan | Filter | Metrik/kolom utama |
|---|---|---|
| Booking | Periode, paket, cabang, agen, status | Nomor, jamaah, paket, total, status |
| Jamaah | Keberangkatan, dokumen, status | Profil, kategori, status kesiapan |
| Penjualan | Periode, produk, agen | Gross, diskon, net, booking |
| Piutang/aging | Tanggal potong, jatuh tempo | Saldo, overdue days, kelompok umur |
| Pembayaran | Periode, rekening, petugas | Nomor, verified amount, referensi |
| Kas/bank | Rekening, periode | Saldo awal, masuk, keluar, akhir |
| Komisi | Agen, periode, status | Nilai earned, approved, paid |
| Kuota | Paket, departure | Capacity, booked, available, waitlist |
| Profit keberangkatan (P1) | Departure | Revenue, direct cost, margin |

Setiap laporan menampilkan kriteria filter, cap waktu as-of jika perlu, total yang dapat direkonsiliasi, dan pilihan CSV/XLSX/PDF sesuai izin.

### MOD-14 — Operasional Perjalanan [P1]
- **Hotel:** master hotel, negara/kota, booking confirmation, tanggal check-in/out, tipe kamar, capacity dan rooming list; peringatan over-capacity dan konflik penempatan.
- **Transport/tiket:** maskapai, flight leg, PNR/booking ref, jadwal, pembagian rombongan, perubahan penerbangan.
- **Visa:** tipe visa, nomor referensi, tanggal pengajuan/terbit, status proses, expiry, lampiran; integrasi resmi hanya setelah verifikasi.
- **Perlengkapan:** master item, alokasi per jamaah, status serah-terima dan bukti penerimaan.
- **Manasik dan itinerary:** lokasi, jadwal, petugas/pembimbing, pengingat.
- **Supplier:** master vendor, purchase order sederhana, tagihan pemasok, pembayaran, alokasi ke keberangkatan.

### MOD-15 — Akuntansi [P1]
- COA, periode buku, jurnal double-entry, posting dan reversal, pengaturan akun default.
- Auto-journal dari invoice, penerimaan pembayaran, biaya, komisi, refund sesuai kebijakan akuntansi yang disetujui.
- Neraca saldo, buku besar, jurnal umum, laba rugi, neraca, arus kas (metode sesuai konfigurasi).
- Penutupan periode; transaksi backdate diblokir kecuali periode dibuka kembali oleh otoritas terkait.
- Biaya dan pendapatan dikaitkan dengan departure agar analisis profit akurat; kebijakan pengakuan pendapatan perlu ditentukan bersama akuntan.

### MOD-16 — Pembatalan, Refund & Perubahan Jadwal [P1]
- Ajukan pembatalan dengan alasan, timestamp, tarif penalti menurut kontrak dan tanggal kejadian.
- Kalkulasi refundable amount transparan, mempertimbangkan pembayaran diterima, penalti, vendor nonrefundable dan pajak/fee terkait.
- Approval berjenjang, refund melalui rekening asal/destinasi terverifikasi, lampiran bukti.
- Reschedule harus menahan kursi jadwal baru secara atomik dan mengembalikan kursi lama setelah sukses.
- Pencatatan delta harga, refund/additional invoice, dampak komisi dan audit log.

### MOD-17 — Portal Agen [P1] & Portal Jamaah [P0]
- Agen: dashboard prospek/booking sendiri, link referral, upload dokumen jamaah dengan mandat, laporan komisi.
- Jamaah: melihat paket dipesan, checklist, jadwal perjalanan, pembayaran, invoice, notifikasi; perubahan biodata sensitif harus diverifikasi.
- Semua akses menggunakan scopes tenant/cabang/booking yang benar, tanpa ekspos jamaah lain.

### MOD-18 — Integrasi [P1] & Notifikasi Inti [P0]
- Event internal: booking.created, invoice.issued, payment.verified, document.rejected, departure.updated, refund.approved.
- Notifikasi melalui email/WhatsApp/SMS berdasarkan persetujuan dan template, antrean retry serta status delivery.
- Payment gateway: callback ditandatangani, idempotent, nominal dan referensi cocok, anti-double-posting.
- SISKOPATUH: hanya melalui akses/prosedur resmi yang disetujui, tanpa mengasumsikan API publik tersedia. Jika hanya *deep link*, labeli sebagai tautan keluar bukan sinkronisasi.
- API untuk integrasi terpisah dari admin internal dan dijaga token scoped, logging, throttling.

### MOD-19 — CRM (P2)
- Lead source, owner, tahap NEW/CONTACTED/QUALIFIED/QUOTED/WON/LOST.
- Jadwal follow-up, aktivitas, alasan kehilangan dan konversi menjadi booking.
- Atribusi agen dan dashboard conversion funnel; deduplikasi calon jamaah.

## 7. Alur Kerja Utama (End-to-End)

### 7.1 Setup dan penjualan
1. Super Admin mengisi profil perusahaan, cabang, rekening, pengguna, izin.
2. Admin produk membuat paket dan satu atau beberapa jadwal keberangkatan.
3. Operator menetapkan kapasitas, harga, aturan DP, checklist dokumen.
4. Agen/CS mendaftarkan jamaah dan membuat booking; seat direservasi atomik.
5. Sistem menerbitkan invoice dan jadwal pembayaran.
6. Finance mencatat dan memverifikasi pembayaran; booking berubah status sesuai aturan.

### 7.2 Persiapan dan perjalanan
1. Staf dokumen menerima berkas dan menandai VERIFIED/REJECTED.
2. Operasional menyusun manifest, kamar, tiket, visa, perlengkapan (sesuai modul tersedia).
3. Sistem memvalidasi readiness gate: pembayaran, dokumen, kuota, approval pengecualian.
4. Admin berwenang menandai READY_TO_DEPART, lalu DEPARTED.
5. Setelah perjalanan selesai, keberangkatan menjadi COMPLETED dan biaya final direkonsiliasi.

### 7.3 Komisi dan laporan
1. Kebijakan komisi dievaluasi saat trigger kelayakan terjadi.
2. Finance memeriksa daftar komisi yang layak.
3. Approver menyetujui, petugas membayar, bukti dicatat.
4. Owner membuka laporan penjualan, piutang, biaya dan profit per keberangkatan.

## 8. Business Rules (Lintas Modul)

| Rule ID | Aturan |
|---|---|
| BR-001 | Nomor jamaah, booking, invoice, kwitansi dan payment unik dalam scope yang ditetapkan |
| BR-002 | Seat tidak boleh negatif dan dipesan memakai transaksi DB/locking atau constraint atomik |
| BR-003 | Harga booking di-*snapshot*; perubahan master tidak merevisi transaksi historis |
| BR-004 | Total invoice tidak boleh negatif tanpa jenis dokumen kredit yang sesuai |
| BR-005 | Pembayaran belum terverifikasi tidak mengurangi outstanding resmi |
| BR-006 | Reversal wajib terhubung ke transaksi original; tidak boleh silent delete |
| BR-007 | Pembatalan booking memerlukan kalkulasi seat, invoice, refund, komisi dan rekonsiliasi |
| BR-008 | Jamaah tidak boleh dinyatakan siap berangkat jika syarat mandatory gagal tanpa approved exception |
| BR-009 | Tidak ada perubahan dokumen terverifikasi tanpa revisi/riwayat baru |
| BR-010 | Hak akses diterapkan pada row, field, action, ekspor, file attachment, dan API |
| BR-011 | Setiap perubahan data keuangan dan konfigurasi sensitif memiliki audit trail |
| BR-012 | Semua tanggal bisnis disimpan konsisten (UTC di DB, tampil Asia/Jakarta) |
| BR-013 | Nominal disimpan sebagai DECIMAL, bukan floating point |
| BR-014 | Penyimpanan identitas harus mengikuti kebijakan retensi dan regulasi perlindungan data yang berlaku |
| BR-015 | Semua proses finansial yang diulang karena retry memiliki idempotency key |

## 9. Model Data Konseptual

| Entitas | Kolom kunci dan relasi |
|---|---|
| companies | id, name, contact, legal_info |
| branches | id, company_id, code, name, address |
| users | id, branch_id, role_id, name, email, password_hash, status |
| roles / permissions | id, code, action, resource; role_permissions |
| pilgrims | id, code, biodata, identity fields, emergency_contact |
| pilgrim_documents | id, pilgrim_id, type, file_id, expiry, status, reviewer_id |
| agents | id, code, name, branch_id, commission_policy_id |
| packages | id, code, name, category, description, status |
| package_prices | id, package_id, room_type, price, valid_from/to |
| departures | id, package_id, depart_at, return_at, capacity, status |
| bookings | id, booking_no, departure_id, agent_id, payer_id, total, status |
| booking_participants | id, booking_id, pilgrim_id, room_type, seat_status, price_snapshot |
| invoices / invoice_lines | id, booking_id, invoice_no, total, due_date, status; line details |
| payment_schedules | id, invoice_id, due_date, amount, milestone |
| payments | id, invoice_id, bank_account_id, amount, paid_at, status, reference |
| bank_accounts | id, branch_id, bank_name, account_no_encrypted, status |
| cash_transactions | id, account_id, direction, amount, category, payment_id, booking_id |
| agent_commissions | id, booking_id, agent_id, basis, rate, amount, status |
| hotels / rooms / allocations | hotel, room capacity, departure/participant assignment (P1) |
| visas / flights | departure, pilgrim, refs, dates, status (P1) |
| expenses / suppliers | supplier_id, departure_id, amount, approval state |
| gl_accounts / journal_entries / journal_lines | Accounting (P1), balanced entries |
| notifications | id, channel, recipient, template, status, tries |
| audit_logs | id, actor_id, entity, record_id, action, before/after diff, time |
| attachments | id, storage_key, checksum, mime, owner_scope, sensitivity |

**Relasi utama:** `company 1:N branch`, `package 1:N departure`, `departure 1:N booking`, `booking 1:N booking_participant`, `pilgrim 1:N booking_participant`, `booking 1:N invoice`, `invoice 1:N payment`, `booking 0..1 agent` (atau multi-attribution terpisah jika diperlukan).

**Rekomendasi indeks:** unique pada nomor bisnis; index `(departure_id, status)`, `(invoice_id, status)`, `(agent_id, status)`, `(pilgrim_id)`, `(branch_id, created_at)`. File disimpan di object storage; database hanya menyimpan metadata dan referensi.

## 10. Sitemap dan Rancangan Halaman

```text
LOGIN
DASHBOARD
MASTER DATA
  ├─ Perusahaan & Cabang
  ├─ Rekening Kas/Bank
  ├─ Pengguna & Hak Akses
  ├─ Jamaah
  ├─ Agen
  ├─ Paket & Harga
  ├─ Vendor, Hotel, Maskapai (P1)
OPERASIONAL
  ├─ Jadwal Keberangkatan
  ├─ Pendaftaran / Booking
  ├─ Checklist Dokumen
  ├─ Manifest Jamaah
  ├─ Rooming List (P1)
  ├─ Tiket & Visa (P1)
  ├─ Perlengkapan (P1)
KEUANGAN
  ├─ Invoice & Termin
  ├─ Penerimaan Pembayaran
  ├─ Kas & Bank
  ├─ Pengeluaran
  ├─ Komisi Agen
  ├─ Refund (P1)
  ├─ Jurnal & Buku Besar (P1)
LAPORAN
  ├─ Booking & Penjualan
  ├─ Jamaah & Manifest
  ├─ Piutang / Aging
  ├─ Penerimaan & Kas Bank
  ├─ Komisi Agen
  ├─ Profit Keberangkatan (P1)
PENGATURAN
  ├─ Identitas & Template Dokumen
  ├─ Nomor Dokumen
  ├─ Kebijakan Pembayaran & Komisi
  ├─ Integrasi / Notifikasi (P1)
  ├─ Audit Log
```

### 10.1 UI/UX requirement
- Admin dashboard desktop-first, responsif pada tablet; mobile mendukung tugas inti baca/input sederhana.
- Navigasi sidebar, breadcrumb, pencarian global terbatas permission, filter tersimpan opsional.
- Semua tabel: sort, filter, pagination server-side, bulk action aman, empty state, loading/error state, ekspor sesuai izin.
- Semua form: label jelas, required marker, validasi inline, deteksi perubahan belum disimpan, konfirmasi untuk tindakan destruktif.
- Kartu status dibedakan teks dan ikon, tidak bergantung warna saja; contrast dan keyboard accessibility sesuai WCAG 2.2 AA sebagai target.
- Data penting menunjukkan *last updated*, operator terakhir, dan histori jika memiliki izin.
- Form panjang dibagi tab: Identitas, Kontak, Paspor, Dokumen, Riwayat, Pembayaran.

## 11. API Contract Awal (Usulan)

Base: `/api/v1`; semua endpoint membutuhkan autentikasi kecuali login/public.

| Method | Endpoint | Kegunaan |
|---|---|---|
| POST | `/auth/login` | Autentikasi |
| POST | `/auth/logout` | Akhiri sesi |
| GET/POST | `/users` | Daftar/buat pengguna |
| GET/POST | `/pilgrims` | Daftar/buat jamaah |
| GET/PATCH | `/pilgrims/{id}` | Detail/update jamaah |
| POST | `/pilgrims/{id}/documents` | Unggah dokumen |
| POST | `/pilgrims/{id}/documents/{docId}/review` | Verifikasi/tolak |
| GET/POST | `/packages` | Master paket |
| GET/POST | `/departures` | Jadwal dan kuota |
| GET/POST | `/bookings` | Booking dan daftar |
| POST | `/bookings/{id}/confirm` | Konfirmasi booking |
| POST | `/bookings/{id}/cancel` | Pembatalan terotorisasi |
| GET/POST | `/invoices` | Tagihan |
| POST | `/payments` | Catat pembayaran |
| POST | `/payments/{id}/verify` | Verifikasi oleh otoritas |
| GET/POST | `/agents` | Master agen |
| GET | `/commissions` | Daftar komisi |
| POST | `/commissions/{id}/approve` | Persetujuan |
| GET/POST | `/cash-transactions` | Kas/bank |
| GET | `/reports/receivables` | Laporan piutang |
| GET | `/departures/{id}/manifest` | Manifest sesuai permission |
| GET | `/audit-logs` | Audit log sesuai role |

**Standar API:** JSON, pagination cursor atau offset konsisten, sort whitelist, filter, validation errors per field, correlation ID, OpenAPI 3.x, idempotency key untuk create payment/refund, rate limit, RFC 7807-style error opsional.

## 12. Keamanan, Privasi dan Kepatuhan

- Meminimalkan pengumpulan NIK, paspor, data kesehatan dan identitas sensitif; pembatasan eksplisit berdasarkan kebutuhan operasional.
- Enkripsi data in transit (TLS) dan at rest; secret tidak tersimpan pada repositori.
- Password disimpan menggunakan algoritme hashing aman (Argon2id atau setara), MFA untuk akun privileged (P1).
- Pengujian OWASP ASVS sesuai profil risiko; perlindungan CSRF, XSS, injection, SSRF, upload exploit, broken object-level authorization.
- Log perubahan mencatat siapa, kapan, data apa; log tidak menyimpan password, OTP, atau nomor kartu pembayaran.
- Kebijakan retensi, penghapusan/anonymization dan permintaan subjek data perlu disepakati menurut ketentuan hukum Indonesia yang relevan.
- Backup terenkripsi dengan tes pemulihan rutin; pemisahan lingkungan dev, staging dan production.
- Ekspor data sensitif memakai otorisasi, watermark opsional dan audit log.
- SISKOPATUH dan dokumen perizinan mengikuti prosedur resmi instansi; **jangan mengklaim integrasi sudah tersedia tanpa uji**.

## 13. Non-Functional Requirements

| NFR | Target usulan | Verifikasi |
|---|---|---|
| Availability | 99,5% bulanan untuk MVP | Monitoring uptime |
| Latensi API | p95 < 800 ms untuk GET standar pada beban target | Load test |
| Dashboard | p95 < 3 detik pada koneksi normal | Browser RUM/test |
| Kapasitas awal | 20 concurrent staff, 100.000 profil jamaah dengan indexing memadai | Performance test |
| Integritas | 0 overbooking dan pembayaran double-post | Concurrency/idempotency tests |
| Recovery | RPO ≤ 24 jam, RTO ≤ 8 jam pada MVP; tingkatkan saat kontrak SLA dibuat | Restore drill |
| Keamanan | Kritis/tinggi diselesaikan sebelum produksi | SAST/DAST/pentest |
| Auditability | Seluruh financial posting dan approval dapat ditelusuri | QA audit trail |
| Lokalitas | Bahasa Indonesia, format tanggal/nominal Indonesia | QA UI |
| Aksesibilitas | Target WCAG 2.2 AA untuk alur inti | Audit aksesibilitas |

Angka kapasitas dan SLA harus dikonfirmasi melalui estimasi traffic, anggaran dan infrastruktur aktual.

## 14. Kriteria Penerimaan End-to-End (UAT)

| UAT ID | Skenario | Expected result |
|---|---|---|
| UAT-01 | Admin membuat paket dan departure kapasitas 20 | Paket dan departure muncul, kapasitas 20 |
| UAT-02 | Dua petugas serentak mengambil kursi terakhir | Tepat satu booking berhasil reserve seat |
| UAT-03 | CS mendaftarkan 3 orang keluarga | Satu booking, tiga participant unik, nilai benar |
| UAT-04 | Harga paket berubah setelah booking | Invoice existing tidak berubah |
| UAT-05 | Upload paspor kurang masa berlaku | Warning/hold sesuai kebijakan tanggal perjalanan |
| UAT-06 | Dokumen ditolak petugas | Alasan wajib dan status kembali perlu revisi |
| UAT-07 | Pembayaran DP belum diverifikasi | Outstanding resmi belum berkurang |
| UAT-08 | Pembayaran sama dikirim dua kali (retry) | Hanya satu transaksi finansial terposting |
| UAT-09 | Agen menerima komisi setelah syarat tercapai | Komisi sesuai snapshot policy dan status eligible |
| UAT-10 | Booking dibatalkan | Kursi kembali; invoice, refund, komisi ditangani konsisten |
| UAT-11 | User cabang A mengakses data cabang B | Ditolak sesuai izin |
| UAT-12 | Kasir mencoba menyetujui transaksi sendiri | Ditolak jika maker-checker aktif |
| UAT-13 | Finance ekspor aging piutang | Totals konsisten dengan invoice/pembayaran verified |
| UAT-14 | Cetak manifest berdasarkan departure | Hanya jamaah pada departure dan field berizin |
| UAT-15 | Reversal pengeluaran terposting | Histori asli utuh dan saldo benar |
| UAT-16 | File dengan ekstensi palsu / payload berbahaya | Diblokir upload pipeline |
| UAT-17 | Laporan owner filter satu periode/cabang | Seluruh widget/ekspor memiliki filter identik |
| UAT-18 | Akun nonaktif mencoba autentikasi | Tidak bisa masuk atau akses API |

## 15. Rekomendasi Arsitektur Teknis

> Arsitektur berikut adalah **usulan implementasi**, bukan identifikasi framework dari aplikasi referensi.

**Opsi utama:** Django + Django REST Framework (backend), PostgreSQL (database), React/Next.js atau Django Templates + HTMX (frontend admin), Redis + Celery (job asinkron), storage S3-compatible (file), Nginx (reverse proxy), Docker (deployment). Pilihan dapat disesuaikan dengan keterampilan tim dan kompleksitas UI.

**Komponen:**
1. Web app admin, opsional portal agen/jamaah.
2. REST API modular berlapis services + permission + validators.
3. PostgreSQL dengan transaksi DB untuk booking kursi dan pembayaran.
4. Background workers untuk email, notifikasi, pembuatan dokumen dan ekspor besar.
5. Object storage privat untuk dokumen; signed URL dan antivirus scan.
6. Audit log append-only/semi-immutable, centralized structured logs, metrics dan tracing.
7. Queue/outbox pattern untuk menjamin event bisnis tidak hilang ketika transaksi DB commit.

**Alternatif:** Odoo Community dengan custom addons jika organisasi ingin akuntansi/ERP terpadu; perlu kajian kecocokan lisensi, standar model data dan kompleksitas kustomisasi.

## 16. Prioritas Backlog (User Stories)

| Story ID | User story | Prioritas |
|---|---|---|
| US-001 | Sebagai admin, saya dapat membuat user dan mengatur hak akses | P0 |
| US-002 | Sebagai admin paket, saya dapat membuat paket dan departure | P0 |
| US-003 | Sebagai CS, saya dapat mendaftarkan grup jamaah | P0 |
| US-004 | Sebagai CS, saya melihat seat tersisa real time dan tidak overbook | P0 |
| US-005 | Sebagai petugas dokumen, saya dapat memverifikasi berkas | P0 |
| US-006 | Sebagai finance, saya dapat mencatat dan memverifikasi pembayaran | P0 |
| US-007 | Sebagai owner, saya melihat booking dan piutang per departure | P0 |
| US-008 | Sebagai admin, saya dapat mencetak manifest dan amplop KBIH | P0 |
| US-009 | Sebagai finance, saya melihat komisi agen yang eligible | P0 |
| US-010 | Sebagai finance, saya mengajukan pengeluaran dan mencatat kas bank | P0 |
| US-011 | Sebagai operasional, saya menyusun rooming list | P1 |
| US-012 | Sebagai akuntan, saya menutup buku dan melihat laporan keuangan | P1 |
| US-013 | Sebagai jamaah, saya melihat status perjalanan saya sendiri | P1 |
| US-014 | Sebagai manajer, saya menyetujui refund dan reschedule | P1 |
| US-015 | Sebagai sales, saya mengelola prospek hingga menjadi booking | P2 |

## 17. Tahapan Delivery dan Dependensi

| Fase | Deliverables | Dependensi |
|---|---|---|
| Discovery & validasi | Audit demo authenticated, BPMN, inventaris layar, field dictionary | Akses stabil ke demo dan stakeholder |
| Design foundation | Design system, role matrix, ERD final, API design | Hasil discovery |
| Sprint cluster A | Login, perusahaan, cabang, master data, paket, departure | Foundation |
| Sprint cluster B | Booking, kuota, invoice, pembayaran, dokumen | Cluster A |
| Sprint cluster C | Agen/komisi, kas-bank, manifest, laporan, audit | Cluster B |
| UAT dan hardening | UAT, concurrency testing, pentest, backup/restore test, training | Semua P0 |
| P1 berikutnya | Operasional rinci, akuntansi, refund, integrasi, portal | MVP stabil |

Durasi dan biaya tidak ditetapkan karena ukuran tim, persyaratan detail dan akses referensi belum terverifikasi. Estimasi dilakukan setelah discovery.

## 18. Risiko, Mitigasi, dan Open Questions

| Risiko | Dampak | Mitigasi |
|---|---|---|
| Aplikasi demo tidak dapat diaudit | Menu/field asli tidak diketahui | Jadwalkan audit browser dengan akses stabil; tandai gap [R]/[U] |
| Aturan DP/refund berbeda tiap travel | Salah status dan saldo | Kebijakan configurable dan disetujui finance/legal |
| Overbooking pada request paralel | Operasional terganggu | DB transaction, lock, constraint, stress test |
| Salah posting penerimaan/komisi | Saldo dan margin keliru | Maker-checker, immutable ledger, reconciliation |
| Kebocoran paspor/identitas | Risiko hukum dan reputasi | Scope akses, encryption, access logging, retention |
| Integrasi Kemenag tidak tersedia | Tidak bisa otomatis sinkronisasi | Adapter opsional, prosedur manual sah |
| Banyak format laporan | Scope creep | Definisikan template resmi dan ownership KPI |
| Pengakuan revenue belum disepakati | Profit dan laporan keuangan keliru | Workshop kebijakan akuntansi |

**Pertanyaan keputusan saat discovery:**
1. Apakah hanya Umroh, atau termasuk Haji Reguler/Khusus dan KBIH?
2. Apakah multi-cabang/multi-company benar-benar diperlukan untuk MVP?
3. Bagaimana kebijakan DP, deposit booking, refund dan penalti?
4. Apa field wajib jamaah dan dokumen berdasarkan produk dan aturan terkini?
5. Apakah agen bertingkat, pembagian komisi, dan referral diperlukan?
6. Daftar laporan cetak dan contoh format asli yang perlu direplikasi?
7. Apakah wajib integrasi SISKOPATUH atau hanya ekspor manifest/manual?
8. Akuntansi double-entry untuk MVP atau tahap selanjutnya?
9. Sistem ditujukan untuk satu travel (single tenant) atau SaaS multi-tenant?
10. Berapa rata-rata booking, jamaah dan pengguna aktif per bulan?

## 19. Definition of Done

Sebuah fitur dinyatakan selesai apabila: acceptance criteria lulus; permission dicek di backend; unit/integration test disertakan; semua perubahan penting memiliki audit log; loading/error/empty state tersedia; dokumentasi API dan manual singkat terbarui; tidak ada isu keamanan kritis/tinggi yang terbuka; validasi UAT disetujui product owner.

## 20. Checklist Audit Fitur Aplikasi Referensi (Belum Diverifikasi)

Gunakan daftar berikut saat login demo dapat diakses. Jangan menyamakan item checklist dengan fitur eksisting.

- [ ] Screenshot dashboard, sidebar dan seluruh submenu.
- [ ] Inventaris form master data beserta field wajib, validasi dan aksi.
- [ ] Daftar paket serta pembuatan/edit paket.
- [ ] Data jadwal, status kursi, alur booking dan registrasi.
- [ ] Master jamaah dan persyaratan dokumen.
- [ ] Data agen dan rumus komisi.
- [ ] Invoice, penerimaan kas/bank, kuitansi, pengeluaran.
- [ ] Jenis laporan yang tersedia beserta filter dan contoh hasil ekspor.
- [ ] Cetak amplop dan dokumen KBIH.
- [ ] Pengaturan pengguna/role dan akses menu.
- [ ] Mekanisme SISKOPATUH apakah tautan keluar atau sinkronisasi.
- [ ] Teknologi frontend/backend hanya jika dapat diidentifikasi secara sah.
- [ ] Audit error state, responsivitas, dan pengalaman pengguna.

## 21. Sumber Referensi

1. Demo publik Amsol SIM-Umroh V2: https://demov2.softwareumroh.com/
2. Halaman produk: https://softwareumroh.com/produk
3. Website produsen: https://softwareumroh.com/
4. Dokumentasi/tutorial terkait paket, agen, pengguna, bank, KBIH: https://softwareumroh.com/biro-travel-umroh

**Catatan akhir:** Dokumen ini dirancang untuk dijadikan dasar discovery, estimasi, backlog, desain sistem dan development. Tidak boleh dipresentasikan sebagai replika 1:1 dari semua fitur internal pada demo tanpa validasi autentikasi dan inspeksi layar.


---

# BAGIAN II — PERSYARATAN TAMBAHAN UNTUK MODEL SaaS MULTI-TENANT (VERSI 2.0)

> **Konvensi:** Semua kemampuan pada bagian ini berlabel **[S]** yaitu persyaratan produk baru untuk SaaS, bukan klaim tentang fitur yang ada pada Amsol. Bagian II menambah atau memperketat ketentuan Bagian I. Bila bertentangan, ketentuan isolasi data, keamanan, billing, dan lifecycle SaaS pada Bagian II berlaku.

## 22. Visi, Sasaran dan Batas Produk SaaS [S]

### 22.1 Outcome bisnis
Membuka layanan mandiri untuk banyak travel dengan biaya operasional platform yang efisien, onboarding cepat, recurring revenue, dan kontrol tenant yang dapat diaudit. Tetap mempertahankan seluruh domain fungsional travel Bagian I sebagai modul produk tenant.

| Persona | Pekerjaan utama | Akses |
|---|---|---|
| Platform Super Admin | Kelola tenant, paket, operasional platform dan incident | Control plane; akses data bisnis tenant tidak otomatis diberikan |
| Platform Billing Admin | Langganan, invoice platform, refund, rekonsiliasi | Data billing platform, bukan data jamaah |
| Platform Support | Tangani tiket, diagnosis tenant setelah persetujuan | Metadata teknis; impersonation terbatas dan diaudit |
| Owner/Admin Travel | Daftar tenant, konfigurasi organisasi, undang staf, atur langganan | Tenant sendiri |
| Finance Travel | Pembayaran jamaah, pembukuan tenant | Tenant sendiri, sesuai izin |
| Operations Travel | Paket, keberangkatan, jamaah, dokumen | Tenant sendiri, sesuai izin |
| Agen Travel | Referral, calon jamaah, komisi yang diizinkan | Cakupan agen pada tenant terkait |
| Jamaah | Lihat status pendaftaran, invoice/dokumen sendiri | Rekaman sendiri dalam tenant |

### 22.2 KPI awal (hipotesis, validasi pilot)
| KPI | Target awal | Cara ukur |
|---|---|---|
| Onboarding hingga workspace aktif | ≤ 10 menit tanpa manual approval untuk kasus standar | Event signup → tenant_activated |
| Isolasi tenant | 0 insiden akses silang tenant | Security tests dan audit |
| Keberhasilan top-up wallet | ≥ 98% callback valid terproses idempotently | Ledger + webhook monitoring |
| Availability aplikasi | 99,9% per bulan, tidak termasuk maintenance terjadwal yang disepakati | Synthetic monitoring |
| RPO / RTO | RPO ≤ 24 jam, RTO ≤ 8 jam untuk MVP; tingkatkan setelah uji DR | Simulasi restore |
| Tersedianya ekspor tenant | 100% permintaan ekspor yang sah dapat diproses | Job export audit |

## 23. Ruang Lingkup dan Prioritas SaaS [S]

**P0 / MVP wajib:** tenant provisioning mandiri tanpa biaya bulanan/setup, identitas/isolasi tenant, wallet deposit dan top-up, verifikasi pembayaran top-up via gateway, idempotent wallet ledger, tarif berversi Rp50.000 per jamaah, pendeteksian DP yang diterima dan terverifikasi, pemotongan tepat sekali per booking-jamaah, status *pending_charge* jika saldo kurang, pengingat saldo, laporan pemakaian, koreksi/refund terotorisasi, reconciliation, billing platform, audit, ekspor, backup dan monitoring.

**P1:** postpaid untuk tenant terpilih dengan limit kredit dan kontrak; diskon progresif berdasarkan volume, custom domain, WhatsApp berbayar, multi-cabang, invoice pajak lebih rinci, bulk import, integrasi DP otomatis, dan support impersonation dengan persetujuan.

**P2:** white-label penuh, SSO, dedicated database, API publik, add-on berbayar, SLA enterprise dan negosiasi tarif berdasarkan kontrak.

**Di luar MVP:**** marketplace paket umroh antar-travel, gateway pembayaran sendiri sebagai institusi keuangan, otomasi langsung ke sistem pemerintah tanpa akses API resmi, dan akses lintas tenant untuk analitik jamaah.

## 24. Multi-Tenancy dan Identitas Tenant [S]

### 24.1 Model pilihan
- **MVP:** satu deployment aplikasi dan satu cluster PostgreSQL, tabel operasional menyimpan `tenant_id` wajib (`NOT NULL`), dengan PostgreSQL Row-Level Security (RLS) sebagai lapisan proteksi tambahan di atas authorization aplikasi. Semua foreign key tenant sensitif diproteksi constraint gabungan `(tenant_id, id)` bila sesuai.
- **Enterprise masa depan:** dukung adapter database-per-tenant; tidak wajib pada MVP. Jangan membuat klaim bahwa shared-database berarti setara isolasi fisik.
- **Tenant ID** berupa UUID immutable; `slug` unik untuk subdomain; perubahan slug tidak mengubah identitas dan membutuhkan redirect serta pembaruan integrasi.
- Semua objek termasuk file, job, audit event, cache key, search index, report export, dan backup wajib terikat konteks tenant; data global platform dibedakan secara eksplisit.
- Gunakan `tenant_id` dari konteks identitas terautentikasi yang diverifikasi server, **bukan** dari query/body yang disuplai klien sebagai sumber kebenaran.

### 24.2 Resolusi dan proteksi konteks tenant
1. Request masuk ke `slug.domainplatform.com`, domain terverifikasi, atau route control plane.
2. Middleware memetakan host ke tenant aktif melalui registry domain terkelola.
3. Autentikasi mengeluarkan identitas pengguna; backend memverifikasi membership pengguna pada tenant dan status tenant.
4. Otorisasi mengecek permission + entitlement plan + status subscription + ownership record.
5. DB transaction menetapkan context tenant pada session/transaksi (misalnya `SET LOCAL` dengan validasi) agar RLS mengikat semua query.
6. Response tidak boleh memuat cache atau attachment tenant lain.

**Aturan:** `Platform Super Admin` bukan tenant wildcard pada aplikasi operasional. Break-glass hanya untuk kebutuhan operasional resmi, membutuhkan alasan, approval, expiry, least privilege dan immutable audit. Domain kustom harus diverifikasi kepemilikannya sebelum aktivasi.

### 24.3 Uji isolasi wajib
- Tenant A tidak dapat membaca/mengubah objek B walaupun menebak UUID/ID; respons konsisten (404/403 sesuai standar).
- Pengguna anggota A dan B dapat pindah workspace setelah memilih secara eksplisit; seluruh konteks/cache di-reset.
- Job Celery/Bull/background workers tidak boleh berjalan tanpa konteks tenant yang eksplisit dan terverifikasi.
- Object storage menggunakan prefix atau bucket strategy berbasis tenant serta signed URL dengan TTL pendek.
- Query laporan, search, autocomplete, aggregate, import/export dan admin action dilindungi tenant filter dan pengujian kebocoran silang.
- Audit platform boleh melihat metadata kesehatan tenant tanpa menampilkan PII jamaah secara default.

## 25. Registrasi, Provisioning dan Lifecycle Tenant [S]

### 25.1 Alur self-service
`Landing Page → Registrasi gratis → Verifikasi email → Nama travel & slug → Persetujuan S&K/DPA → Provision tenant → Setup awal → Dashboard travel → Top-up saldo → Konfirmasi jamaah setelah DP sah`.

**Fields:** nama travel, nama owner, email, telepon, password / SSO nanti, slug, negara/zona waktu, alamat usaha (opsional pada trial), NPWP/identitas usaha jika dibutuhkan untuk invoice, persetujuan syarat layanan & privasi (versi dan timestamp).

**Aturan:** email unik sebagai principal global tetapi dapat menjadi anggota beberapa tenant; nama perusahaan tidak harus unik; slug global unik dan memakai reserved words blacklist; pembuatan tenant dan penetapan owner dilakukan atomik/idempotent; pendaftaran berulang tidak membuat duplikasi tenant.

### 25.2 State machine tenant
`provisioning → active → restricted → suspended → pending_deletion → deleted`; `provisioning → failed` bila gagal. Pemulihan yang diizinkan: `failed → provisioning`, `restricted/suspended → active`, `pending_deletion → active` selama periode pembatalan penghapusan yang berlaku. Status tenant dipisahkan dari subscription dan payment status.

| Status | Perilaku |
|---|---|
| Provisioning | Tidak dapat dipakai sampai setup/entitlements selesai |
| Trial (wajib P0) | Mode demo 30 hari, maksimum 20 booking-jamaah dummy dan 3 user internal; tidak ada DP nyata, charging, atau wallet deduction |
| Active | Akses operasional; transaksi DP terverifikasi dikenakan biaya berdasarkan wallet |
| Restricted | Deposit tidak cukup: konfirmasi booking berbayar tertunda; baca data dan kelola booking aktif tetap diizinkan |
| Suspended | Read-only minimal untuk owner (billing, ekspor yang sah, bantuan) tanpa transaksi operasional baru |
| Pending deletion | Akses aplikasi dibekukan; proses retention dan job delete disiapkan |
| Deleted | Data dihapus sesuai retensi dan kewajiban hukum; tombstone audit minimum tanpa PII |

**Provisi otomatis:** pembuatan tenant, domain bawaan, konfigurasi default, timezone Asia/Jakarta, mata uang IDR, owner membership, trial, defaults roles, storage namespace, event log. Provisioning harus aman diulang, transaksional/seperti saga, menandai error dan menyediakan retry.

### 25.3 Restriction, suspend, hapus
- Trial demonstrasi wajib tersedia untuk tenant baru selama 30 hari sesuai §52. Tidak ada renewal subscription atau biaya bulanan. Setelah trial, akun otomatis menjadi Active (gratis hingga terjadi verified-DP-charge pada booking nyata); biaya Rp50.000 timbul hanya untuk booking-jamaah produksi yang memenuhi pemicu. Tidak ada suspend otomatis karena trial berakhir.
- Saldo wallet tidak cukup **tidak** otomatis menyebabkan tenant disuspend; hanya proses finalisasi konfirmasi baru yang tertahan pada `pending_charge`, dengan notifikasi top-up.
- Suspend hanya untuk pelanggaran ketentuan, keamanan, fraud atau terminasi sesuai prosedur dengan audit dan mekanisme banding; proses layanan untuk jamaah yang sudah aktif harus diperhatikan.
- Terminasi atas permintaan owner membutuhkan verifikasi, ekspor data, penyelesaian kewajiban wallet, penanganan saldo tak terpakai sesuai ketentuan hukum/kontrak, retensi dan audit penghapusan.
- Masa retensi final ditetapkan melalui review legal dan kebijakan perlindungan data Indonesia sebelum produksi.

## 26. Tarif Pay-per-Jamaah, Entitlement dan Metering [S]

### 26.1 Kebijakan komersial yang telah disepakati
| Parameter | Keputusan produk | Prioritas |
|---|---|---|
| Tarif standar | **Rp50.000 per booking-jamaah yang DP-nya telah diterima serta terverifikasi** | P0 |
| Biaya bulanan/tahunan | **Rp0**, tidak ada auto-renewal atau minimum bulanan | P0 |
| Biaya setup standar | **Rp0** | P0 |
| Pemicu charging | Transisi pembayaran DP tenant menjadi `verified/posted` dan booking eligible | P0 |
| Waktu charging | Saat DP pertama yang sah diverifikasi; maksimal sekali per identitas booking-jamaah | P0 |
| Metode penagihan | **Prepaid wallet tenant** | P0 |
| Pengisian saldo | Virtual Account/QRIS/metode payment gateway yang tersedia, setelah konfirmasi sah | P0 |
| Volume discount | Belum berlaku; skema progresif bersifat usulan P1 | P1 |
| Postpaid enterprise | Tidak berlaku MVP, memerlukan persetujuan risiko dan kontrak terpisah | P1 |

**Definisi billable unit:** satu kombinasi unik `tenant_id + booking_passenger_id` (pendaftaran seseorang pada sebuah paket/keberangkatan). Master jamaah yang sama dapat mengikuti dua perjalanan berbeda dan dikenakan biaya sekali pada tiap booking-jamaah; mengganti jadwal atau memperbaiki data tidak otomatis menimbulkan charge baru. Pindah paket oleh booking yang sama wajib mempertahankan identitas asal atau memiliki aturan migrasi eksplisit agar tidak double charge.

**Tidak billable:** lead, master jamaah, draft, booking belum DP, pembayaran DP masih pending/unverified/rejected, perubahan data, pelunasan, dan keberangkatan. **Billable:** booking-jamaah yang memiliki bukti DP diterima dan dinyatakan valid melalui mekanisme verifikasi otoritatif tenant. Pembayaran DP sebagian tetapi sah sudah memicu satu charge; pembayaran DP berikutnya tidak mengulang charge.

### 26.2 Matriks keadaan dan edge case
| Kejadian | Perlakuan billing |
|---|---|
| Buat master jamaah / leads / draft | Rp0 |
| Booking aktif tanpa DP terverifikasi | Rp0 |
| DP tercatat namun belum diverifikasi | Rp0 |
| DP pertama sukses dan terverifikasi | Charge Rp50.000 tepat satu kali |
| DP dibayar dua tahap / lunas / pindah tanggal | Tidak ada charge tambahan untuk booking-jamaah yang sama |
| Webhook ganda atau verifikasi ulang | Tidak mengulangi charge |
| DP dibatalkan sebelum verifikasi | Rp0 |
| Batal setelah DP dan charge sudah terjadi | Charge tetap; kompensasi jika disetujui mengikuti kebijakan di §27.6 |
| Impor booking yang sudah punya DP dari sistem lain | Flag `migration_review`; operator memberi keputusan billable dan tanggal efektif; jangan charge diam-diam |
| Saldo wallet kurang | `pending_charge` dan konfirmasi akhir tertunda, tanpa saldo negatif atau kehilangan data DP |

### 26.3 Entitlement dan fair-use
- Fitur inti travel tersedia pada tarif standar, tanpa tier subscription wajib. Terapkan fair-use terpublikasi pada jumlah user, rate API, storage dan notifikasi untuk mengendalikan biaya; **batas final TBD**, bukan pembatas tersembunyi.
- Penyimpanan dan WhatsApp berbiaya tinggi dapat menjadi add-on P1 dengan persetujuan eksplisit, tidak mengubah tarif dasar.
- Harga ditetapkan oleh `RateCard` berversi dengan `effective_at`; booking menyimpan `rate_snapshot` ketika charge dicatat. Perubahan tarif tidak retroaktif.
- Perbandingan nilai paket Rp30 juta terhadap Rp50 ribu (±0,167%) hanya contoh pemasaran, bukan jaminan bahwa biaya dibayar langsung oleh jamaah. Travel bertindak sebagai pihak yang membayar platform dan dapat memasukkan biaya ke pricing paket secara sah, transparan, dan sesuai regulasi.

## 27. SaaS Wallet, Billing dan Payment Gateway [S]

### 27.1 Pemisahan dana dan ledger
- **Ledger SaaS milik platform:** `Tenant → Wallet → TopUpIntent → TopUpSettlement → WalletLedger(credit) → ChargeEvent → WalletLedger(debit) → Adjustment`. Ledger harus append-only, menggunakan integer IDR dan rekonsiliasi terjadwal.
- **Ledger Travel:** `BookingPassenger → Invoice Travel → DP Payment → Verification → Kas/Bank Tenant`. Dana DP jamaah mengalir kepada travel, **bukan** ke wallet atau rekening platform; platform hanya menerima top-up wallet SaaS.
- **Sumber charging:** status terverifikasi transaksi DP milik travel, bukan redirect browser dan bukan hanya event pembuatan jamaah.

### 27.2 Alur utama top-up dan charge
1. Owner/Finance tenant mengajukan nominal top-up, melihat biaya gateway/pajak yang berlaku sebelum konfirmasi.
2. Platform membuat `topup_intent` dengan external reference unik; gateway menerima pembayaran.
3. Webhook ditandatangani, diverifikasi dan didedup; setelah status paid/settled yang memenuhi aturan, sistem menambah saldo satu kali.
4. Staff travel mencatat DP jamaah; Finance memverifikasi penerimaan dengan lampiran/referensi bank atau payment gateway travel.
5. Transaksi DP diposting ke pembukuan travel. Backend menguji status booking, siapa penerima DP, charge eligibility, serta uniqueness charge.
6. Dalam satu transaksi database, lock wallet, pastikan available balance ≥ Rp50.000 dan belum ada charge, buat usage event dan ledger debit, tandai `charged` serta simpan snapshot tarif.
7. Jika wallet tidak cukup, simpan DP valid dan booking pada status `dp_verified_pending_saas_charge`; **jangan membatalkan DP, jangan membuat saldo minus, jangan menghapus booking**. Setelah top-up, reprocess queue secara aman dan berurutan.
8. Bukti pemotongan ditampilkan di riwayat penggunaan dan laporan platform; tenant dapat menelusuri pemotongan ke booking-jamaah tanpa platform membuka PII yang tidak perlu.

### 27.3 Kebijakan penguncian ketika saldo kurang
- Tetap mengizinkan login, baca/ekspor data, pencatatan DP dan akses booking yang sebelumnya sudah berbayar.
- Tidak mengizinkan finalisasi konfirmasi booking-jamaah baru sampai charge berhasil; status pending jelas di UI serta dapat diproses ulang otomatis/manual.
- Alert saldo saat saldo ≤ batas rendah yang dapat diatur dan saat pending charge terbentuk. Jangan menahan layanan kritis jamaah aktif karena saldo sementara habis.

### 27.4 Ketahanan transaksi
- DB constraint unik `(tenant_id, booking_passenger_id, charge_type)` dengan charge_type=`first_verified_dp`; `idempotency_key` unik untuk tiap top-up/webhook/charge.
- Gunakan atomic `SELECT FOR UPDATE` pada wallet dan transaksi, atau strategi setara, untuk mencegah double-spend; saldo dihitung dari ledger atau materialized balance yang diverifikasi.
- Webhook gateway tervalidasi signature, replay, amount dan currency; inbox/outbox pattern; retry dengan backoff serta dead-letter queue.
- Debit wallet dan event charge harus atomik; bila terjadi error, rollback keduanya. Proses refund/koreksi membuat entry kompensasi, tidak mengedit/menghapus ledger lama.
- Rekonsiliasi harian: saldo ledger vs balance cache, top-up vs gateway settlement, charge vs DP valid, pending vs queue, serta anomali per tenant.

### 27.5 Jenis tagihan dan dokumen
- Bukti/top-up invoice SaaS dipisah dari kuitansi DP travel. Tidak ada invoice langganan bulanan wajib.
- Platform menyediakan kuitansi top-up, mutasi wallet, bukti penggunaan per booking, laporan bulanan penggunaan, credit note/adjustment bila berlaku.
- PPN, perlakuan saldo deposit dan penerbitan dokumen fiskal memerlukan kajian akuntansi/pajak sebelum go-live; jangan menganggap top-up otomatis identik pendapatan yang sudah diakui.

### 27.6 Pembatalan, refund dan koreksi
- **Keputusan MVP:** charge yang telah timbul setelah DP sah **tidak otomatis dikembalikan ketika jamaah batal**, karena layanan aplikasi telah terpakai. Kebijakan ini harus ditampilkan sebelum tenant menerima S&K.
- Bila DP ternyata salah verifikasi, duplikasi booking, fraud, atau kegagalan sistem, Finance Platform dapat menyetujui wallet credit/adjustment dengan reason code, bukti, four-eyes approval pada nominal signifikan, serta audit immutable.
- Refund saldo top-up yang tersisa saat tenant berhenti beroperasi mengikuti ketentuan kontrak, kebijakan AML/KYC bila relevan, metode pembayaran, pajak dan ketentuan hukum; jangan menjanjikan refund otomatis tanpa pemeriksaan.

### 27.7 Contoh hitung
- Tenant top-up Rp1.000.000 (di luar biaya kanal pembayaran jika dikenakan) → saldo wallet Rp1.000.000.
- 1 jamaah bayar DP terverifikasi → charge Rp50.000 → saldo Rp950.000.
- 19 booking-jamaah eligible berikutnya → 19 × Rp50.000 → saldo Rp0.
- Booking ke-21 dengan DP valid → status `pending_charge`, menunggu top-up; transaksi DP travel tetap tercatat.

### 27.8 Acceptance criteria khusus charging
1. Lead/booking tanpa DP sah tidak dikenakan charge.
2. Satu booking-jamaah hanya menghasilkan satu charge walau DP bertahap/webhook digandakan.
3. Dua transaksi DP bersamaan tidak membuat saldo negatif atau pemotongan ganda.
4. Top-up yang dikirim webhook berulang hanya meningkatkan saldo satu kali.
5. Ketika saldo tidak cukup, DP valid tersimpan dan booking pending; setelah top-up charge diproses tepat sekali.
6. Perubahan tarif tidak mengubah charge historis.
7. Charge/refund dapat ditelusuri dari mutasi wallet sampai sumber event tanpa mengungkap data tenant lain.


## 28. Control Plane Platform Owner [S]

### 28.1 Modul administrasi platform
| ID | Modul | Kemampuan | P |
|---|---|---|---|
| SAAS-01 | Overview SaaS | Total tenants, volume jamaah billable, top-up, pendapatan pemakaian, saldo wallet, onboarding funnel | P0 |
| SAAS-02 | Tenant Directory | Cari tenant, status, plan, domain, owner, created at, feature usage; suspend/reactivate terotorisasi | P0 |
| SAAS-03 | Tenant Provisioning | Manual create, retry failed job, verifikasi domain | P0 |
| SAAS-04 | Rate Card & Entitlement | CRUD tarif per jamaah berversi, fair-use, fitur dan publikasi perubahan | P0 |
| SAAS-05 | Wallet & Usage Billing | Top-up, pemotongan per DP, settlement, rekonsiliasi, adjustment, refund approval | P0 |
| SAAS-06 | Support Center | Ticket, kategori, prioritas, SLA internal, catatan tanpa PII | P0 |
| SAAS-07 | Usage & Capacity | Storage, jumlah pengguna, jamaah, data growth, alert anomali | P0 |
| SAAS-08 | Security & Audit | Platform log, suspicious login, akses support, policy, log export | P0 |
| SAAS-09 | Announcements | Maintenance & product announcement, template email transaksional | P1 |
| SAAS-10 | Branding / Domains | Custom domain, DNS proof, certificate lifecycle | P1 |
| SAAS-11 | Finance Analytics | Cohort MRR, revenue, failed payments, churn, ARPA | P1 |
| SAAS-12 | Integrations | Gateway config, email/WA service, provider callback health | P0 dasar / P1 lanjut |

**Batas peran:** billing admin tidak bisa mengekspor dokumen jamaah, support tidak bisa mengubah data keuangan travel, platform analytics tidak bisa meng-query PII pelanggan tenant tanpa tujuan dan hak akses yang sah.

### 28.2 Tenant Console
Owner Travel mengelola profil usaha, lokasi, logo, rekening bisnis travel, anggota tim dan izin, workspace/domain, berlangganan (plan, invoice dan metode pembayaran), usage dan limit, security settings, activity log, export request, support ticket, serta penghapusan akun/perusahaan dengan verifikasi.

## 29. Role, Membership dan Delegasi Akses [S]

- Akun identitas global (`users`) terpisah dari relasi tenant (`tenant_memberships`) sehingga seorang konsultan bisa mendapat akses resmi ke lebih dari satu travel.
- Roles ditetapkan **per tenant**; role platform sepenuhnya terpisah dan disimpan di realm/namespace berbeda.
- Default: `owner`, `admin`, `finance`, `operations`, `agent`, `viewer` (per tenant); paket dapat membatasi jumlah seat, bukan secara diam-diam mengurangi izin data saat tagihan macet.
- Undangan email: token single-use, masa berlaku, domain dan tenant terikat, revoke/resend, acceptance audit.
- Owner terakhir tidak boleh dihapus sebelum ownership transfer diverifikasi.
- MFA wajib untuk Platform Super Admin dan sangat direkomendasikan/wajib untuk Owner Travel sebelum aksi berisiko (ekspor besar, pembayaran, delete, transfer owner).
- Session logout/revoke khusus tenant atau global; akses dicabut segera setelah membership dinonaktifkan.
- Impersonation support (P1) memerlukan approval owner, tujuan dan waktu akses, banner terlihat, identitas operator tetap ada di audit; tidak boleh dapat mengekspor data tanpa izin tambahan.

## 30. White Label, Domain dan Branding [S]

- MVP setiap tenant memiliki subdomain `slug.nama-platform.id` (domain contoh, domain produksi ditentukan terpisah), logo, warna dasar, header dokumen dan info legal travel sendiri.
- P1 mendukung custom domain via DNS TXT challenge, CNAME/A sesuai arsitektur, validasi kepemilikan, TLS otomatis, pembaruan domain, rollback dan pencegahan domain takeover.
- Email transaksi dapat menggunakan domain/platform default; custom sender domain (SPF/DKIM/DMARC) adalah P1 dengan verifikasi.
- Branding sama untuk portal jamaah, invoice travel, dan notifikasi tenant, tetapi dokumen legal langganan tetap diterbitkan pemilik platform.

## 31. Platform Notifications, Support dan Reliability [S]

- Notifikasi: signup verification, welcome, trial ending, invoice issued, payment success/failure, grace, suspend/reactivate, nearing quota, security events, deletion confirmation.
- Kanal MVP: email; WA/WhatsApp API resmi P1. Gunakan job queue, retry exponential backoff, DLQ, template berversi, preference center untuk notifikasi non-esensial.
- Support: user submit tiket terikat tenant; lampiran wajib dipindai; masking PII default; SLA internal ditampilkan sesuai plan.
- Status page dan incident communications P1; di MVP setidaknya ada in-app maintenance banner dan kanal status email.
- Observability: per-tenant request rate, job latency, failed webhook, error budgets dan quota exhaustion tanpa memasukkan data sensitif ke log.

## 32. Migrasi dan Portabilitas Data [S]

- Import data tenant dari XLSX/CSV untuk jamaah, paket, agen, pembayaran dengan validation preview, kolom mapping, dry run, dedupe dan rollback batch.
- Ekspor minimum: master jamaah, jadwal, paket, booking, invoice travel, payment, agen, dokumen serta audit metadata yang diizinkan; unduhan arsip terenkripsi melalui short-lived signed link.
- Job ekspor memverifikasi hak owner/role khusus, status tenant, batas ukuran dan memerlukan MFA pada ekspor sensitif.
- Tenant suspended bisa mengajukan ekspor data sesuai kebijakan kontrak, privasi dan kewajiban hukum; tidak diperbolehkan menghapus akses ke data tanpa proses portabilitas yang dijanjikan.
- Restorasi hanya satu tenant wajib tidak menimpa atau memulihkan record tenant lain; desain recovery dari backup shared DB memerlukan tooling pemisahan/pemulihan dengan validasi referential integrity.

## 33. Skema Data SaaS Tambahan [S]

| Entitas / tabel | Field penting | Catatan |
|---|---|---|
| `tenants` | id UUID, name, slug, status, timezone, currency, created_at | Identitas immutable |
| `tenant_domains` | tenant_id, hostname, verification_status, tls_status | Unique hostname |
| `tenant_settings` | tenant_id, logo_path, branding, invoice_defaults | Tenant scoped |
| `users` | id, email, password_hash, email_verified_at, mfa_status | Global principal |
| `tenant_memberships` | tenant_id, user_id, role_id, status, invited_at | Unique `(tenant_id,user_id)` |
| `platform_role_assignments` | user_id, platform_role_id | Tidak mewarisi izin tenant |
| `subscription_plans` | id, code, version, status, billing_interval, currency | Immutable published plan version |
| `plan_features` | plan_id, feature_key, enabled, limit_value | Catalogue |
| `subscriptions` | id, tenant_id, plan_version_id, status, start_at, period_end_at, cancel_at | Riwayat tidak ditimpa |
| `subscription_changes` | subscription_id, old_plan, new_plan, effective_at, reason | Audit |
| `saas_invoices` | id, tenant_id, number, subtotal, tax, total, status, due_at | **Berbeda dari invoice jamaah** |
| `saas_invoice_items` | invoice_id, description, qty, unit_price, tax | Basis hitung invoice |
| `saas_payments` | id, invoice_id, gateway, gateway_ref, amount, status, paid_at | Idempotent unique external ref |
| `gateway_webhook_events` | provider, external_event_id, payload_hash, processed_at, status | Dedup, minimalkan payload PII |
| `usage_events` | tenant_id, metric, quantity, occurred_at, dedup_key | Append-only |
| `usage_counters` | tenant_id, metric, period, used, calculated_at | Rekonsiliasi tersedia |
| `feature_overrides` | tenant_id, feature_key, value, expires_at, approved_by | Aturan dan expiry eksplisit |
| `saas_audit_logs` | actor, tenant_id(nullable), action, resource, metadata, timestamp | Append-only / tamper evident |
| `support_tickets` | id, tenant_id, reporter, status, priority, assigned_to | Metadata tanpa PII secara default |
| `export_jobs` | tenant_id, requester_id, status, artifact_path, expires_at | Terenkripsi, audit |
| `tenant_deletion_requests` | tenant_id, requested_by, approved_at, execute_after, legal_hold | Retensi |

**Migration rule:** seluruh tabel Bagian I yang spesifik travel (jamaah, paket, keberangkatan, pesanan, dokumen, agen, kas, jurnal dan report jobs) wajib menyimpan `tenant_id`, indeks/unique constraints disesuaikan menjadi tenant-scoped. Contoh `UNIQUE(tenant_id, booking_number)`; jangan hanya membuat nomor global acak dan mengandalkan filter UI.

## 34. API SaaS (Rancangan Awal) [S]

| Metode | Endpoint | Otorisasi |
|---|---|---|
| POST | `/api/v1/public/signup` | Publik + anti-abuse |
| POST | `/api/v1/public/verify-email` | Verification token |
| GET | `/api/v1/tenant/me` | Auth + membership |
| POST | `/api/v1/tenant/invitations` | Tenant Owner/Admin |
| GET | `/api/v1/tenant/subscription` | Tenant Owner/Billing role |
| POST | `/api/v1/tenant/subscription/checkout` | Tenant Owner/Billing role |
| POST | `/api/v1/tenant/subscription/change-plan` | Tenant Owner/Billing role |
| GET | `/api/v1/tenant/usage` | Tenant Owner/Admin |
| POST | `/api/v1/tenant/exports` | Tenant Owner + step-up auth |
| GET | `/api/v1/platform/tenants` | Platform admin scoped |
| POST | `/api/v1/platform/tenants/{id}/suspend` | Platform admin + reason |
| GET | `/api/v1/platform/plans` | Platform billing/product admin |
| POST | `/api/v1/platform/plans` | Platform billing/product admin |
| GET | `/api/v1/platform/invoices` | Platform billing admin |
| POST | `/api/v1/webhooks/payments/{provider}` | Verified gateway signature |

**API invariants:** idempotency keys untuk mutasi finansial/provisioning; standard pagination/filtering; response error standar dengan trace ID tanpa bocor metadata tenant lain; rate limits per IP/user/tenant; validation ownership; all endpoints versioned; callback webhook tidak menggunakan auth end-user tetapi signature khusus provider.

## 35. UX dan Sitemap SaaS [S]

```text
PUBLIC
├── Landing / Product / Features / Pricing / FAQ / Contact
├── Sign up / Login / Forgot Password / Verify Email
├── Free Trial Signup / Activate Workspace / Terms & Privacy
└── Help Center / System Status (P1)

PLATFORM CONTROL PLANE (host admin terpisah)
├── Dashboard SaaS
├── Tenants → List / Detail / Lifecycle / Domain / Usage
├── Plans & Features → Catalog / Version / Entitlements
├── Trial Management → Active Trials / Conversion / Limits / Exceptions
├── Billing SaaS → Invoices / Payments / Reconciliation / Credits
├── Support → Tickets / Escalations
├── Security → Access / Audit / Incident Events
├── Configuration → Gateway / Email / Feature Flags
└── Reports → MRR / ARR / Churn / Tenant Growth

TENANT CONSOLE (subdomain tenant)
├── Dashboard Travel (seluruh modul Bagian I)
├── Jamaah / Paket / Keberangkatan / Booking / Dokumen
├── Agen / Komisi / Keuangan Jamaah / Operasional / Laporan
├── Pengaturan Travel → Profil / Bank / Cabang / Branding
├── Tim → Users / Invitations / Roles
├── Langganan → Plan / Upgrade / Invoice SaaS / Usage
├── Keamanan → Password / MFA / Sessions / Audit
└── Bantuan & Data → Tickets / Import / Export / Closure
```

**UX wajib:** tampilkan `nama travel` jelas pada setiap halaman, pemilihan workspace eksplisit bila multi-membership, layar entitlements yang manusiawi (limit dan tombol tindakan), pemisahan jelas `Biaya SaaS Wallet` vs `Invoice Jamaah`, status trial/grace/suspended dan konsekuensinya sebelum terjadi.

## 36. Security, Privacy, Compliance dan Operasi [S]

### 36.1 Kontrol keamanan
- RBAC + object-level authorization; kebijakan deny by default dan least privilege.
- PostgreSQL RLS + integration tests multi-tenant, review migrasi, allowlisted system jobs; gunakan koneksi pool yang tidak mempertahankan context tenant antar-request.
- Password hashing Argon2id atau algoritma setara yang mutakhir; TLS, encryption at rest, secrets manager, rotasi kredensial, MFA platform mandatory.
- Lindungi PII jamaah (identitas, paspor, dokumen perjalanan, pembayaran) dengan minimisasi, field masking, kontrol akses, retention policy, dan redaction log.
- Logging tindakan finansial, penyesuaian status, perubahan akses, ekspor data, impersonation dan delete tidak bisa dimodifikasi operator biasa.
- Backup otomatis terenkripsi, offsite, diuji restore berkala; restore per tenant diuji setidaknya per rilis besar.
- Rate limiting dan bot protection untuk signup/login/email verification; vulnerability scans, dependency checks, pen test sebelum produksi.
- Dokumen kebijakan perlu ditinjau terhadap **UU PDP Indonesia dan aturan terkait yang berlaku**, termasuk pembagian peran pengendali/pemroses data, DPA, notifikasi insiden, dan permintaan subjek data; detail kewajiban hukum harus diverifikasi dengan penasihat hukum.

### 36.2 Reliability dan deployment
- Disarankan Django + Django REST Framework + PostgreSQL + Redis + Celery + object storage S3-compatible, reverse proxy, container deployment dan CI/CD. Ini **rekomendasi**, bukan stack terverifikasi situs referensi.
- Pisahkan layanan/logical modules: Identity & Tenant Control, Subscription Billing, Travel Domain, Notifications, Files, Analytics; **modular monolith pada MVP** lebih realistis daripada microservices prematur.
- Background job wajib memuat tenant context dan idempotency key; scheduled subscription job dieksekusi di platform scope dengan tenant-specific state transitions.
- Storage quota, CPU/IO fair-use, per tenant throttling dan job queue isolation untuk mengurangi noisy neighbor.
- Healthcheck, metrics, structured logs, tracing, alerting billing webhook, DB locks, queue depth, failed provision, storage growth dan backup health.
- Runbook operasional: outage, payment gateway failure, tenant restore, credential compromise, disputed billing, deletion request.

### 36.3 SLO awal
| Kategori | Sasaran MVP | Verifikasi |
|---|---|---|
| Availability | 99,9% / bulan (kebijakan maintenance ditentukan) | Uptime synthetic |
| Latensi API | p95 ≤ 800 ms untuk endpoint CRUD ringan di beban target | Load test |
| Tenant isolation | 0 akses silang data | Authz tests, fuzzing |
| Provisioning | p95 ≤ 2 menit setelah verifikasi email dan input lengkap | Job/event timing |
| Backups | Harian, terenkripsi, restore drill | Monitoring + evidence |
| Capacity | Uji baseline 100 tenant dan 1.000 user aktif (asumsi, bukan sizing final) | Load testing |

## 37. User Stories Prioritas SaaS [S]

| ID | Story | P | Acceptance utama |
|---|---|---|---|
| S-US-01 | Sebagai owner, saya dapat membuat trial tenant sendiri | P0 | Signup terverifikasi, provision tidak duplikat |
| S-US-02 | Sebagai owner, saya memilih slug untuk alamat workspace | P0 | Unik, reserved blocked, DNS/route aktif |
| S-US-03 | Sebagai admin travel, saya mengundang dan mencabut anggota | P0 | Token aman, seat enforced, access revoked |
| S-US-04 | Sebagai owner, saya dapat top-up wallet via payment gateway | P0 | Top-up verified via webhook, no duplicate ledger |
| S-US-05 | Sebagai owner, saya melihat invoice SaaS terpisah | P0 | Invoice benar dan tidak tercampur invoice jamaah |
| S-US-06 | Sebagai owner, saya dapat melihat limit dan usage | P0 | Kategori unit jelas, enforcement atomik |
| S-US-07 | Sebagai tenant A, data tenant B tidak dapat diakses | P0 | Negative test cross-tenant pass |
| S-US-08 | Sebagai platform billing admin, saya menangani pembayaran macet | P0 | Reminder, grace, suspend/recover audit |
| S-US-09 | Sebagai platform admin, saya memantau tenant tanpa melihat PII | P0 | Dashboard metadata-only |
| S-US-10 | Sebagai owner, saya dapat mengekspor data tenant | P0 | Authorized, complete, temporary encrypted link |
| S-US-11 | Sebagai owner, saya dapat upgrade plan | P1 | Efektif sesuai kebijakan dan pembayaran |
| S-US-12 | Sebagai owner, saya dapat menautkan domain sendiri | P1 | DNS challenge + TLS + takeover protections |
| S-US-13 | Sebagai support, saya meminta temporary access | P1 | Owner consent, expiry, audit |
| S-US-14 | Sebagai platform owner, saya dapat menetapkan add-on | P1 | Entitlements + metering + invoice tepat |
| S-US-15 | Sebagai owner, saya mengajukan penutupan tenant | P0 | MFA, retention clock, legal hold, audit |

## 38. UAT dan Test Matrix SaaS [S]

| Test ID | Skenario | Expected result |
|---|---|---|
| T01 | 2 travel mendaftar dengan nama mirip | Tenant ID berbeda, slug global unik |
| T02 | Signup double submit | Tepat satu tenant tercipta |
| T03 | Login A gunakan ID booking B | Akses ditolak tanpa data bocor |
| T04 | Ekspor A filter disusupi tenant B | Tidak ada record B dalam hasil |
| T05 | File URL A dipakai user B | Ditolak/expired tanpa mengungkap file |
| T06 | Worker job A berjalan setelah task B | DB context tidak bocor antar-job |
| T07 | User bergabung 2 tenant lalu switch | Data/menu/cache sesuai tenant terpilih |
| T08 | Tenant capai limit user/storage | New write ditolak tepat, old data utuh |
| T09 | Downgrade plan dengan usage melebihi cap | Data aman, write baru dibatasi |
| T10 | Webhook sukses dikirim 3 kali | Payment dan invoice diposting satu kali |
| T11 | Webhook invalid signature | Tidak terjadi perubahan finansial |
| T12 | Webhook status diacak urutannya | Tidak ada regress pembayaran final |
| T13 | Trial berakhir tanpa top-up | Tenant menjadi Active tanpa biaya bulanan; data demo tetap terpisah/diarsipkan, tidak ada suspend/hapus otomatis |
| T14 | Payment valid diterima setelah suspend | Reactivate dan entitlements pulih |
| T15 | Platform support tanpa consent meminta PII | Denied; access attempt logged |
| T16 | Billing admin melihat data jamaah | Denied |
| T17 | Subscription invoice dan jamaah invoice | Ledger, nomor invoice dan laporan terpisah |
| T18 | Pemilik ekspor data saat suspended | Menurut policy, ekspor terotorisasi bisa dilakukan |
| T19 | Permintaan tenant deletion dengan legal hold | Delete ditunda dan alasan dicatat |
| T20 | Tenant-only restore dari shared DB | Data tenant lain tidak berubah |
| T21 | Custom domain salah verifikasi (P1) | Domain tidak bisa diklaim |
| T22 | Penagihan renewal dan time zone akhir bulan | Periode/invoice konsisten tanpa double billing |
| T23 | Platform admin menjalankan suspend tanpa alasan | Ditolak |
| T24 | Log out/revoke membership | Semua tenant session terkait dihentikan sesuai scope |

**Exit criteria rilis:** semua P0 lulus functional UAT; negative cross-tenant dan pembayaran/webhook diuji otomatis pada CI; restore drill berhasil; pen-test risiko kritis/tinggi ditangani; legal terms, privacy policy, DPA dan kebijakan retention ditinjau; alerting dan incident runbook aktif.

## 39. Roadmap dan Dependensi Implementasi [S]

| Fase | Fokus | Keluaran |
|---|---|---|
| F0 Discovery | Konfirmasi harga, definisi usage, compliance, kebijakan dunning/retention, metode billing | Keputusan produk disetujui |
| F1 Fondasi tenant | Auth global, memberships, tenant registry, RLS, request context, security tests | Multi-tenant core |
| F2 Domain travel | Adaptasi semua modul Bagian I agar tenant-scoped | Operasional travel aman |
| F3 Monetisasi | Pricing Rp50.000/jamaah, trial demo 30 hari, top-up wallet, verified-DP-charge, ledger dan webhook | Revenue flow end-to-end |
| F4 Control plane | Platform dashboards, lifecycle, support, audit, exports, backups | Operator siap produksi |
| F5 Hardening/pilot | Load/security/UAT, tenant restore, observability, onboarding pilot | Go-live gate |
| F6 P1 | Custom domain, proration, add-on, branch, WA, SSO menurut permintaan | Growth capability |

**Dependensi kritis:** tenancy dan security harus selesai **sebelum** adaptasi data/CRUD masif; model entitlement harus disepakati **sebelum** checkout/billing; policy suspend dan data portability harus final **sebelum** menerima pelanggan berbayar.

## 40. Risiko Tambahan dan Keputusan Terbuka [S]

| Risiko / keputusan | Dampak | Tindakan |
|---|---|---|
| Bocor data lintas tenant | Sangat tinggi | RLS, authz semua layer, pentest dan automated negative tests |
| Gangguan gateway / callback tidak valid | Tinggi | Durable webhook inbox, signature, retries, reconciliation |
| Noisy neighbor | Sedang–tinggi | Fair-use, rate limiting, isolation queue, capacity alerts |
| Kebijakan kuota samar | Tinggi | Definisi metrik dan kontrak, contoh UI, grace handling |
| Restore individual tenant sulit | Tinggi | Backup architecture + tested extraction/restore |
| Pajak, DPA, PDP, retensi tidak jelas | Tinggi | Review legal/accounting sebelum public launch |
| Harga dan SKU belum pasti | Sedang | Riset willingness-to-pay dan margin infra/gateway |
| Harga paket berubah tetapi invoice lama hilang | Tinggi | Versioned pricing, immutable invoice |
| Pengguna multi-tenant salah memilih workspace | Sedang | Context banner, safe switch, warning aksi berisiko |

### 40.1 Keputusan produk yang harus dikunci
1. Identitas merek dan domain platform produksi.
2. Segmentasi travel yang disasar (kecil, menengah, enterprise) dan tier harga.
3. Apakah billing berbasis seat, jamaah, storage, transaksi, atau kombinasi; definisi masing-masing.
4. Metode pembayaran, kebijakan pajak, penerbit invoice, failed payment/dunning.
5. Trial sudah diputuskan 30 hari; 20 booking-jamaah dummy; 3 user internal; kebijakan retensi data demo dan ekspor setelah suspend ditinjau sesuai §52.
6. Persyaratan multi-cabang, white label, domain kustom, dan layanan support.
7. Target pilot tenant, kapasitas awal, SLA bisnis, dan batasan data residency.
8. Apakah ada migrasi data lama dan format ekspor interoperabel.

## 41. Definition of Done Khusus SaaS [S]

Fitur SaaS dinyatakan siap ketika skenario positif/negatif lolos, kontrol tenant di server & DB konsisten, event keuangan idempotent, semua error terlacak, audit tersedia, akses RBAC diuji, UI menunjukkan state/limit yang dapat dipahami, API didokumentasikan, tes CI berjalan, monitoring hidup, proses rollback/recovery ada, dan panduan customer support disiapkan.

### Ringkasan batasan sumber
PRD ini merupakan **pengembangan kebutuhan produk SaaS** dari PRD awal berdasarkan referensi situs demo publik; akses login ke demo belum terverifikasi. Tidak ada klaim bahwa tenant management, subscription SaaS, platform billing, isolation, atau fitur [S] lainnya sudah dimiliki aplikasi referensi. Target, paket, dan angka dalam Bagian II adalah **usulan untuk divalidasi**, bukan komitmen komersial final.


# BAGIAN III — PERUBAHAN SILANG MODUL UNTUK PAY-PER-JAMAAH (V3.0)

## 42. Keputusan Arsitektural dan Penggantian Ketentuan V2
**Ketentuan normatif V3.3:** `trial` kembali menjadi requirement MVP **khusus mode demo 30 hari menurut §52**; bukan free trial atas langganan berulang. Istilah `subscription`, `plan upgrade`, `monthly billing`, `MRR`, `ARR`, `past_due` dan `renewal` pada bagian asal V2 adalah artefak historis yang **tidak berlaku untuk MVP**; digantikan dengan `wallet + top-up + verified-DP-charge` menurut §26–§27, §43–§49 dan §52. Modul travel §1–§21 tetap berlaku kecuali diubah eksplisit oleh pasal berikutnya.

## 43. Perubahan Alur Modul Travel
- **MOD-07 Booking:** tambahkan `booking_passenger_id` UUID permanen, `saas_charge_state` (`not_eligible`, `pending_charge`, `charged`, `waived`, `reversed`), timestamps, linked charge event dan `pricing_snapshot`. Jangan menyamakan record master jamaah dengan billable registration.
- **MOD-09 Pembayaran:** verifikasi DP harus menggunakan approval/otoritas finance tenant; status minimal `pending`, `verified`, `rejected`, `reversed`. Penerimaan uang DP dan pemotongan wallet adalah transaksi terpisah; tidak ada silent loss bila saldo kurang.
- **MOD-13 Laporan:** tambahkan jumlah booking DP verified, paid SaaS charge, pending charge, penggunaan bulanan, saldo, mutasi, biaya SaaS per keberangkatan dan ekspor.
- **MOD-16 Refund:** pembatalan DP jamaah tidak otomatis menghapus charge SaaS; reversal approval dan kompensasi wallet mengikuti §27.6.
- **Tenant dashboard:** perlihatkan saldo wallet, prediksi kapasitas saldo dalam jamaah (`floor(balance/active_rate)`), transaksi terbaru, antrian DP yang pending charge, CTA top-up, dan audit per booking.
- **Owner platform:** lihat financial summary penggunaan tanpa akses otomatis ke nama/paspor/PII jamaah.

## 44. Model Data Tambahan / Revisi
| Entitas | Field penting | Constraint & catatan |
|---|---|---|
| `saas_rate_cards` | id, code, amount_idr=50000, currency, effective_at, expires_at, version, active | berversi, tidak mutasi biaya historis |
| `tenant_wallets` | id, tenant_id, currency, balance_minor, version, status | unik tenant + currency, lock saat debit |
| `wallet_ledger_entries` | id, wallet_id, tenant_id, type, amount_signed, balance_after, source_id, idempotency_key, created_at | append-only, unique idempotency key, amount integer |
| `wallet_topups` | id, tenant_id, amount, gateway_provider, gateway_ref, status, settled_at | callback verifikasi & dedup |
| `booking_passengers` (update) | id, tenant_id, booking_id, jamaah_id, dp_verified_at, saas_charge_state | satu penumpang per booking terdaftar |
| `saas_usage_charges` | id, tenant_id, booking_passenger_id, dp_payment_id, rate_card_id, amount, status, charged_at, ledger_entry_id | unique `(tenant_id, booking_passenger_id, charge_type)` untuk charge aktif; reversal sebagai kompensasi |
| `wallet_adjustments` | id, tenant_id, charge_id, reason_code, amount, requested_by, approved_by, evidence, status | separation of duties; audit |
| `usage_reconciliation_runs` | id, run_date, outcome, mismatch_count, report_ref | job terjadwal + alarm anomali |
| `webhook_inbox` | id, provider, external_event_id, payload_hash, verified, processed_at | dedup external event |
| `tenant_rate_overrides` (P1) | tenant_id, rate_card_id, effective_at, contract_id | hanya dengan persetujuan & log |

**DB rules:** seluruh objek operasional memuat `tenant_id`; ledger tidak mengizinkan UPDATE/DELETE dari jalur aplikasi; uang IDR disimpan sebagai `BIGINT` integer rupiah, dan perhitungan pajak/biaya gateway memiliki field terpisah; laporan harus mendukung audit rekonsiliasi.

## 45. API Contract V3 (Usulan)
| Method | Route | Permission | Fungsi |
|---|---|---|---|
| GET | `/api/v1/tenant/wallet` | owner, finance | saldo tersedia dan pending charges |
| GET | `/api/v1/tenant/wallet/ledger` | owner, finance | mutasi paginated, filter rentang tanggal |
| POST | `/api/v1/tenant/wallet/topups` | owner, finance | buat top-up, idempotency-key |
| GET | `/api/v1/tenant/wallet/topups/{id}` | owner, finance | status top-up |
| POST | `/api/v1/webhooks/payments/{provider}` | gateway signed | terima webhook top-up dan dedup |
| POST | `/api/v1/tenant/dp-payments/{id}/verify` | finance approver | verifikasi DP, emit usage event atomik/outbox |
| GET | `/api/v1/tenant/saas/usage` | owner, finance | daftar charge/booking-jamaah |
| GET | `/api/v1/tenant/saas/usage/export` | owner, finance | ekspor rincian sesuai tenant |
| GET | `/api/v1/platform/wallets/reconciliation` | billing platform | pantau mismatch, tanpa PII jamaah |
| POST | `/api/v1/platform/charges/{id}/adjustments` | finance platform | ajukan koreksi dengan approval |
| PUT | `/api/v1/platform/rate-cards/{id}` | super admin | publikasi tarif baru (append/version) |

**Payload contoh charge:** `{"booking_passenger_id":"uuid","dp_payment_id":"uuid","charge_type":"first_verified_dp","rate_id":"v1","amount_idr":50000,"status":"charged"}`. Semua mutasi memakai autentikasi, rate limit, tenant context tervalidasi, audit dan kunci idempotensi.

## 46. Sitemap V3
**Platform:** Overview → Tenants → Rate Cards → Wallet Top-ups → Charge Usage → Reconciliation → Adjustments & Approvals → Support → Audit & Settings.

**Tenant:** Dashboard → Jamaah → Booking → Pembayaran DP → Paket & Keberangkatan → Keuangan Travel → SaaS Wallet (Saldo / Top-up / Mutasi / Penggunaan / Pending Charge) → Laporan → Pengaturan.

Tidak menampilkan layar paket langganan bulanan/upgrade wajib pada MVP.

## 47. Matriks UAT V3 (Wajib Lulus)
| ID | Skenario | Ekspektasi |
|---|---|---|
| PAY-01 | Tambah master jamaah tanpa booking | Tidak terdebit |
| PAY-02 | Buat booking tanpa DP | Tidak terdebit |
| PAY-03 | DP tercatat belum validasi | Tidak terdebit |
| PAY-04 | DP Rp5 juta diterima dan diverifikasi, wallet cukup | Debit tepat Rp50.000 |
| PAY-05 | DP kedua dan pelunasan atas booking-jamaah sama | Tanpa debit baru |
| PAY-06 | Webhook DP/top-up dikirim berulang | Top-up & charge tepat sekali |
| PAY-07 | 2 booking diproses serentak, wallet sisa Rp50.000 | Satu charged, satu pending; saldo ≥ 0 |
| PAY-08 | Wallet Rp0 dan DP sah | DP tercatat, booking pending charge, bisa lihat data |
| PAY-09 | Top-up setelah PAY-08 | Debit otomatis sekali dan booking konfirmasi |
| PAY-10 | Pembatalan setelah DP charged | Tanpa refund SaaS otomatis |
| PAY-11 | Salah verifikasi DP, adjustment disetujui | Ledger kredit kompensasi, tidak menghapus debit |
| PAY-12 | Import jamaah historis sudah DP | Tidak auto-charge tanpa review |
| PAY-13 | Ubah harga standar mendatang | Charge lama tak berubah |
| PAY-14 | API tenant A memuat booking B | Akses ditolak & tak bocor PII |
| PAY-15 | Refund/top-up gateway gagal | Tidak menambah saldo dan tidak charge |
| PAY-16 | Rekonsiliasi wallet harian | Semua perubahan terlacak, mismatch alert |
| PAY-17 | Pindah jadwal pada booking-jamaah yang sama | Tidak membuat tagihan baru |
| PAY-18 | Jamaah sama daftar keberangkatan kedua | Satu charge untuk booking kedua bila DP kedua sah |
| PAY-19 | Finance tanpa otorisasi mencoba override charge | Ditolak, terekam di audit |
| PAY-20 | Owner ekspor ledger/usage | Data hanya tenant sendiri, cocok hasil rekonsiliasi |

## 48. Kebijakan, Risiko, dan Pertanyaan Tersisa
**Keputusan disetujui:** tarif standar Rp50.000, trigger DP terverifikasi, Rp0 langganan bulanan, Rp0 setup standar, prepaid wallet untuk MVP.

**Kebijakan default rancangan yang perlu disahkan sebelum go-live:** apakah biaya gateway top-up ditanggung platform atau tenant; minimum top-up (tidak ditentukan); periode settlement DP yang dianggap sah; bagaimana pengembalian wallet deposit; batas fair-use storage; persetujuan resmi atas pembatalan dan adjustment; apakah dan kapan e-faktur diperlukan; syarat penggunaan dan notifikasi perubahan harga. Tarif Rp50.000 tidak termasuk asumsi pajak tertentu sampai legal/finance menyetujui.

**Risiko khusus:** seasonality volume jamaah, pembayaran DP di luar sistem, penyalahgunaan pembatalan/duplikasi booking, rekonsiliasi wallet, top-up fraud, beban support tidak sebanding dengan penggunaan, serta likuiditas saldo wallet. Mitigasi berupa audit, alur DP yang sangat berguna bagi travel, peringatan anomali, batas fair-use transparan, dan data margin per tenant.

## 49. Roadmap MVP SaaS Monetisasi
1. **Foundation:** tenant isolation, user/RBAC, booking-passenger ID, data dan payment states.
2. **Wallet:** ledger append-only, top-up gateway, webhook inbox, reconciliation.
3. **Charging:** rate card version, trigger DP verified, atomic debit, pending-charge & retry.
4. **UI & Reports:** saldo dan top-up, notifikasi, usage per booking, platform finance control plane.
5. **Hardening:** UAT PAY-01–20, concurrency, backup/restore, tenant security, review legal/pajak, pilot.

**Definition of Done:** charge tepat satu kali setelah DP verified, tidak charge sebelum DP, tidak ada saldo negatif, transparansi saldo & ledger, tidak ada bocor data lintas tenant, exception tercatat dan dapat dipulihkan, dan semua kebijakan monetisasi disetujui untuk rilis.


---

## 50. Penegasan Konsep Monetisasi Sebelum Modul Fitur Tambahan [S] — V3.1

> **Status:** Bagian ini adalah bagian normatif PRD. Mengonsolidasikan seluruh keputusan dan pertimbangan dari diskusi konsep monetisasi (poin 1–4 sebelum daftar fitur tambahan). Bila terjadi pertentangan dengan bagian historis subscription pada V2, bagian ini bersama §26–§27 memiliki prioritas.

### 50.1 Rasional pemilihan pay-per-jamaah (menggantikan sewa bulanan)

- **Masalah:** Travel kecil dan musiman cenderung keberatan dengan komitmen abonemen tetap saat belum memperoleh jamaah.
- **Solusi:** Registrasi dan setup standar **gratis**, biaya platform **Rp50.000 per jamaah per pendaftaran perjalanan yang memenuhi syarat**, **tanpa biaya berlangganan bulanan/tahunan**.
- **Prinsip:** Jika tenant belum memperoleh DP terverifikasi, **tidak ada biaya penggunaan per jamaah**. Biaya bergerak bersama skala usaha; tenant dapat secara sah memasukkan biaya sistem ke dalam struktur harga paket, tanpa klaim bahwa platform secara otomatis menagih jamaah langsung.
- **Value proposition:** “Software Travel Umroh tanpa biaya bulanan. Bayar hanya ketika jamaah membayar DP dan diverifikasi.”
- **Referensi nilai:** Jika paket Rp30.000.000, tarif Rp50.000 setara **sekitar 0,167%** nilai paket; hanya ilustrasi, bukan data aktual travel.

| Dimensi | Alternatif langganan tetap (tidak dipilih untuk MVP) | **Pay-per-jamaah (disetujui)** |
|---|---|---|
| Dasar biaya | Tarif tetap per bulan | Rp50.000 per booking-jamaah dengan DP terverifikasi |
| Tanpa jamaah/DP | Tetap ada kewajiban abonemen | **Rp0 biaya penggunaan** |
| Travel kecil/musiman | Biaya tetap dapat terasa berat | Biaya mengikuti aktivitas usaha |
| Travel besar | Beban lebih mudah diprediksi | Biaya bertumbuh bersama volume; dapat diajukan diskon progresif P1 |
| Penerimaan platform | Pendapatan berulang lebih stabil | Pendapatan bervariasi mengikuti DP dan musim |
| Billing | Per periode kalender | Per event DP terverifikasi, memakai prepaid wallet |

### 50.2 Contoh perhitungan monetisasi dan sensitivitas

**Rumus:** `gross_revenue = SUM(jumlah_booking_jamaah_yang_di-charge × tarif_berlaku)`, untuk tarif default MVP: `jumlah × Rp50.000`.

| Jamaah tertagih / tahun / tenant | Pendapatan kotor tahunan per tenant | Rata-rata ekuivalen per bulan* |
|---:|---:|---:|
| 0 | Rp0 | Rp0 |
| 100 | Rp5.000.000 | Rp416.667 |
| 200 | Rp10.000.000 | Rp833.333 |
| 500 | Rp25.000.000 | Rp2.083.333 |
| 1.000 | Rp50.000.000 | Rp4.166.667 |
| 5.000 | Rp250.000.000 | Rp20.833.333 |

*Angka bulanan adalah rata-rata aritmetis, **bukan** kewajiban tagihan setiap bulan. Semua angka adalah proyeksi bruto sebelum biaya infrastruktur, gateway, pajak, support, diskon, refund/adjustment, dan biaya operasional lainnya.*

**Contoh skala platform:** 10 tenant × 100 jamaah = Rp50 juta/tahun; 25 × 200 = Rp250 juta/tahun; 50 × 300 = Rp750 juta/tahun; 100 × 500 = Rp2,5 miliar/tahun (semua pada tarif Rp50 ribu dan seluruh unit benar-benar memenuhi syarat charge). Harga aktual dapat ditentukan rate card berversi; ilustrasi bukan forecast terjamin.

**Risiko komersial:** Pada 5.000 jamaah/tahun, beban tenant Rp250 juta/tahun dapat memicu perbandingan dengan sistem in-house. P1 boleh memperkenalkan diskon volume *progresif*, misalnya 1–500 Rp50 ribu, 501–2.000 Rp45 ribu, 2.001–5.000 Rp40 ribu, dan di atas 5.000 harga kontraktual. **Tidak berlaku otomatis dalam MVP**; harus ada persetujuan, versi rate card dan kalkulasi hanya untuk unit dalam bracket baru (bukan diskon retroaktif).

### 50.3 Definisi pemicu billing: DP diterima **dan terverifikasi**

| Status / kejadian | Billable? | Perlakuan |
|---|---|---|
| Lead/prospek atau master jamaah dibuat | Tidak | Data boleh dikelola gratis |
| Pendaftaran draft | Tidak | Tidak ada debit |
| Terdaftar, belum membayar | Tidak | Tidak ada debit |
| DP tercatat tetapi menunggu validasi finance | Tidak | Tidak ada debit sampai valid |
| **DP pertama diterima dan diverifikasi** | **Ya** | **Satu debit Rp50.000 per booking-jamaah** (bila saldo cukup) |
| DP tambahan, pelunasan, atau keberangkatan | Tidak lagi | Jangan debit dua kali |
| Batal sebelum DP terverifikasi | Tidak | Tidak ada debit |
| Batal setelah DP terverifikasi dan charge | Sudah billable | Tidak otomatis refund; ikuti persetujuan adjustment (§27.6) |
| Perubahan nama, pembetulan berkas, pindah tanggal dengan booking yang sama | Tidak lagi | Identitas billing harus dipertahankan |

**Definisi unit:** Satu pasangan `(tenant_id, booking_passenger_id)` untuk satu pendaftaran perjalanan. Jamaah yang sama dapat berangkat pada kesempatan berbeda dan menghasilkan dua unit billing berbeda. Trigger baru boleh terjadi pada status `dp_verified` dari verifikasi otoritatif; **DP diterima saja tetapi belum diverifikasi belum boleh di-charge**.

### 50.4 Mekanisme settlement: Prepaid dipilih; postpaid enterprise opsional

**Model A — Prepaid Wallet (P0/MVP):**
1. Tenant mengisi saldo melalui payment gateway (misal Rp1.000.000 untuk kapasitas **20** jamaah pada harga Rp50 ribu).
2. Platform mencatat top-up **sekali saja** setelah settlement gateway tervalidasi, dengan mutasi kredit pada ledger.
3. Tenant mengelola leads dan mendaftarkan jamaah tanpa dikenai biaya penggunaan.
4. Setelah finance mengesahkan DP, charge service memeriksa apakah booking belum pernah dikenai biaya dan saldo mencukupi.
5. Bila cukup, saldo terdebit tepat Rp50.000 dengan transaksi atomik serta event usage/bukti potong; booking dapat dikonfirmasi.
6. Bila kurang, DP tetap dicatat sah dan booking ditandai `dp_verified_pending_saas_charge`; konfirmasi akhir menunggu top-up. Jangan menghapus data, menahan pengelolaan jamaah aktif, atau menjadikan saldo negatif. Proses ulang setelah top-up harus idempotent.
7. Dashboard menampilkan saldo, kapasitas jamaah dari saldo, pemakaian, pending charge, riwayat top-up, dan notifikasi saldo rendah.

**Model B — Postpaid (P1, bukan model standar):** Invoice penggunaan dikonsolidasikan berkala untuk tenant enterprise yang telah diverifikasi, mempunyai kontrak, limit kredit, jadwal settlement, prosedur penagihan dan mitigasi tunggakan. **Tidak boleh aktif tanpa persetujuan tertulis** dan kontrol risiko khusus. Model ini bukan langganan bulanan; invoice berkala hanya merangkum transaksi berdasarkan pemakaian.

**Non-functional acceptance:** Mutasi wallet append-only; seluruh event finansial bersifat atomik dan idempotent; ada deteksi webhook berulang, locking saldo, reconciliation harian, audit, izin peran, ekspor ledger, alert perbedaan, dan pemisahan mutlak dana DP milik travel dari dana top-up SaaS milik platform.

### 50.5 Keputusan implementasi dan traceability

| Ketentuan | Lokasi kebutuhan teknis | UAT minimal |
|---|---|---|
| Gratis sebelum DP verified | §26.1–§26.2, §43 | PAY-01 s.d. PAY-04 |
| Satu charge Rp50.000 per booking-jamaah | §26, §27.3, §44–§45 | PAY-04, PAY-06, PAY-07 |
| Top-up dan prepaid wallet | §27.1–§27.2, §44–§46 | PAY-05, PAY-08, PAY-09 |
| Wallet tak cukup tidak menghapus DP | §27.2, §43 | PAY-08, PAY-09 |
| Pembatalan dan koreksi terkontrol | §27.6, §44 | PAY-10, PAY-11 |
| Transparansi usage dan saldo | §28, §46 | PAY-16, PAY-20 |
| Postpaid hanya P1 enterprise | §26.1 dan bagian ini | Test persetujuan kontrak sebelum aktivasi |

**Keputusan final yang sudah disetujui:** Tarif dasar Rp50.000; per booking-jamaah; pemicu **DP diterima dan diverifikasi**; prepaid wallet MVP; Rp0 setup standar; Rp0 biaya langganan tetap. **Hal yang masih TBD:** minimum top-up, pembebanan biaya gateway/pajak, ambang saldo rendah, SLA verifikasi DP, kebijakan pengembalian deposit dan struktur diskon enterprise. Tidak boleh disimpulkan sudah disetujui hanya berdasarkan contoh di atas.


---

## 51. Konfirmasi Lima Fitur Operasional Wajib SaaS (v3.2)

**Status:** normative; bagian ini melengkapi MOD-07/08/09/12/13/14/15/17/18 dan mengungguli klasifikasi prioritas lama apabila tidak konsisten. Semua fitur inti di bawah adalah **P0 / MVP** dan **termasuk dalam tarif pemakaian Rp50.000 per jamaah dengan DP terverifikasi**, tanpa biaya bulanan maupun add-on wajib. Integrasi layanan pihak ketiga yang berbiaya, seperti WhatsApp Business, dapat memiliki biaya pass-through yang dinyatakan transparan; jalur notifikasi dasar via email tetap tersedia tanpa biaya add-on. Fitur yang tercantum sebagai P1 tidak boleh menjadi prasyarat untuk mengoperasikan proses inti P0.

### 51.1 FT-01 — Invoice dan kuitansi otomatis [P0]

**Tujuan:** mencegah pembuatan tagihan manual dan menghadirkan bukti pembayaran yang konsisten serta dapat diaudit.

**Functional requirements**
- `INV-01` Ketika booking sah disimpan, sistem otomatis membuat invoice berdasarkan *snapshot* harga paket, peserta, diskon, tambahan layanan dan skema termin DP/cicilan/pelunasan; tidak membuat duplikasi saat event diproses ulang.
- `INV-02` Invoice memiliki nomor unik **per tenant**, tanggal, identitas legal travel, nomor booking, identitas penagih, rincian jamaah dan layanan, total, jatuh tempo, nominal pembayaran, dan saldo tagihan; branding/logo tenant tersedia.
- `INV-03` Invoice dapat diunduh/cetak PDF; invoice yang telah diterbitkan tidak boleh ditimpa diam-diam. Koreksi menggunakan void/credit note/revisi berversi sesuai otorisasi.
- `INV-04` Saat pembayaran DP/cicilan/pelunasan **telah diverifikasi**, sistem menerbitkan **kuitansi otomatis bernomor unik** yang mengacu pada pembayaran dan invoice; transaksi gagal/draft tidak menghasilkan kuitansi final.
- `INV-05` Satu pembayaran terverifikasi menghasilkan maksimal satu kuitansi final; proses webhook/retry tidak menghasilkan kuitansi atau pemotongan wallet duplikat.
- `INV-06` Kirim invoice/kuitansi secara otomatis ke portal dan email jamaah, dengan catatan delivery serta fitur kirim ulang manual sesuai hak akses.
- `INV-07` DP jamaah dicatat pada pembukuan **tenant**; biaya SaaS Rp50.000 dipotong pada **wallet SaaS tenant** melalui proses terpisah setelah verifikasi DP. Kuitansi pembayaran jamaah tidak boleh dicampur dengan invoice/top-up SaaS.

**Acceptance criteria:** invoice dibuat sekali pada booking; PDF terbuka dengan data sesuai database; verifikasi pembayaran membuat satu kuitansi; mengulang webhook 3x tidak membuat dokumen ganda; koreksi mempertahankan riwayat; hanya jamaah yang berhak dapat mengunduhnya.

### 51.2 FT-02 — Portal jamaah, upload dokumen, dan status [P0]

**Akses:** URL portal berlingkup tenant, login terautentikasi (undangan/OTP sesuai mekanisme produk), jamaah hanya melihat booking miliknya dan anggota keluarga yang diberikan akses secara eksplisit. Akses tautan undangan berlaku terbatas, tidak menjadi link publik permanen.

**Functional requirements**
- `POR-01` Dashboard jamaah menampilkan paket, tanggal keberangkatan, progress administratif, status pembayaran, invoice/kuitansi, checklist dokumen dan informasi kontak travel.
- `POR-02` Upload paspor, KTP, foto, kartu keluarga dan berkas lain berdasarkan checklist dinamis; validasi ukuran/MIME/scan malware; objek tersimpan privat, akses menggunakan signed URL berumur pendek.
- `POR-03` Staf berwenang menerima/menolak dokumen dengan alasan. Status terlihat oleh jamaah (`Belum unggah`, `Menunggu verifikasi`, `Perlu perbaikan`, `Terverifikasi`) dan tersedia versi/history.
- `POR-04` Progress memiliki timeline jelas: `Terdaftar → Menunggu DP → DP terverifikasi → Dokumen dilengkapi → Siap berangkat → Berangkat → Selesai`; status booking dan status dokumen ditampilkan terpisah agar tidak menyesatkan.
- `POR-05` Jamaah dapat mengunduh invoice/kuitansi dan membaca informasi jadwal, manifest personal (hanya informasi miliknya), dan pengumuman travel.
- `POR-06` Perubahan data identitas penting memerlukan permintaan perubahan dan verifikasi admin, bukan mengubah data manifest secara langsung.
- `POR-07` Portal tidak boleh membocorkan data jamaah lain, wallet SaaS tenant, atau data travel lain melalui UI, API, ID berurutan, atau URL file.

**Acceptance criteria:** upload file berhasil kemudian status `Menunggu verifikasi`; penolakan menampilkan alasan dan menyediakan unggah ulang; jamaah A tidak bisa mengakses dokumen atau invoice jamaah B, termasuk melalui API; semua perubahan audit-able.

### 51.3 FT-03 — Pembayaran, manifest, dan keberangkatan [P0]

**Functional requirements**
- `OPS-01` Pembayaran memiliki termin, pencatatan bukti, status verifikasi, alokasi ke invoice, outstanding dan histori koreksi, mengikuti MOD-09.
- `OPS-02` Verifikasi DP memicu **satu** charge Rp50.000 per booking-jamaah melalui prepaid wallet. Jika saldo tidak cukup, pembayaran DP tetap tercatat; booking menuju `dp_verified_pending_saas_charge` sampai top-up; jamaah aktif tidak dihapus atau diblokir dari layanan keselamatan/kegiatan yang sudah berlangsung.
- `OPS-03` Manifest otomatis tersusun dari peserta yang terhubung ke satu keberangkatan dan dapat dipilah berdasarkan rombongan, paket, status kesiapan, pembayaran dan dokumen. Akses identitas/paspor dibatasi role.
- `OPS-04` Manifest memiliki tampilan dan ekspor PDF/XLSX/CSV, dengan versi waktu, penerbit, serta audit ekspor data pribadi. Revisi manifest memperbarui data sumber yang tepat dan menyimpan jejak perubahan.
- `OPS-05` Admin operasional menetapkan jadwal, kapasitas, koordinator, titik kumpul dan status keberangkatan minimal `DRAFT → OPEN → READY → DEPARTED → COMPLETED` (atau `CANCELED`). Kapasitas tidak boleh terlampaui tanpa otorisasi.
- `OPS-06` Perubahan jadwal penting dapat memicu notifikasi kepada jamaah yang terdampak. Sistem menampilkan gate kesiapan: pembayaran, dokumen wajib dan persetujuan pengecualian sesuai konfigurasi travel.
- `OPS-07` P1: rooming list, visa workflow mendalam, tiket penerbangan, vendor dan itinerary kompleks tetap berada di MOD-14, dan bukan syarat P0.

**Acceptance criteria:** DP diverifikasi memperbarui pembayaran tanpa duplikasi charge; manifest sesuai daftar booking saat filter diterapkan; perubahan departure berotorisasi dan terekam; tidak bisa menandai READY bila dokumen wajib belum lengkap kecuali approved exception.

### 51.4 FT-04 — Notifikasi otomatis kepada jamaah [P0]

**Functional requirements**
- `NTF-01` Gunakan *event-driven notification queue* pada event: booking berhasil, invoice terbit, DP diverifikasi, kuitansi terbit, dokumen diterima/ditolak, pelunasan, dan perubahan jadwal keberangkatan.
- `NTF-02` Sediakan inbox notifikasi di portal serta pengiriman email transaksi sebagai kanal dasar P0. WhatsApp/SMS dengan provider resmi menjadi P1/opsional, termasuk template approval, persetujuan penerima dan transparansi biaya pesan.
- `NTF-03` Template memiliki variabel tenant, nama jamaah, booking, nominal, tanggal serta link aman; tenant dapat mengubah teks yang diizinkan tanpa menghilangkan informasi wajib.
- `NTF-04` Antrean memiliki idempotency/deduplication key, status `PENDING/SENT/FAILED`, retry dengan backoff dan dead-letter queue; kegagalan email tidak membatalkan pencatatan DP atau wallet charge yang sah.
- `NTF-05` Audit mencakup jenis pesan, penerima, waktu, hasil, sumber event; jangan mencatat isi dokumen sensitif ke log notifikasi. Atur preferensi pesan non-transaksional dan kepatuhan perlindungan data.

**Acceptance criteria:** verifikasi DP memicu satu pesan transaksi logis per event dan kanal, meskipun event diproses ulang; kegagalan provider memunculkan retry; pengguna mendapat informasi jadwal terbaru; tidak ada data tenant lain dalam payload.

### 51.5 FT-05 — Laporan operasional dan keuangan siap pakai [P0]

**Functional requirements**
- `RPT-01` Dashboard operasional: total jamaah per periode/paket, booking, DP terverifikasi, checklist dokumen, okupansi kursi, manifest dan status kesiapan tiap keberangkatan.
- `RPT-02` Dashboard keuangan praktis: omzet invoiced, pembayaran terverifikasi, tagihan outstanding/aging, kas/bank masuk-keluar, pengeluaran per kategori/keberangkatan, dan ringkasan margin estimasi yang diberi label `estimasi` bila biaya belum lengkap.
- `RPT-03` Setiap laporan memiliki preset rentang tanggal, cabang, paket, keberangkatan, status; kolom subtotal/total, timestamp `as of`, serta ekspor PDF/XLSX/CSV sesuai izin.
- `RPT-04` KPI keuangan harus dapat direkonsiliasi terhadap invoice, payment verified, credit/reversal dan kas/bank. Keuangan tenant dipisahkan tegas dari saldo/prepaid wallet dan pendapatan platform SaaS.
- `RPT-05` Laporan ringkas tenant atas biaya SaaS: saldo wallet, top-up, jumlah booking-jamaah yang sudah dikenai charge, total biaya Rp50.000 per unit, daftar tertunda dan mutasi per periode; drill-down ke transaksi.
- `RPT-06` Sistem mendukung pencetakan langsung/unduh untuk pimpinan atau staf tanpa perlu membuat formula spreadsheet sendiri. Akuntansi double-entry lengkap (buku besar, neraca, laba rugi formal) tetap P1 pada MOD-15.

**Acceptance criteria:** setiap total laporan cocok dengan transaksi sumber pada tanggal potong yang sama; filter cabang dan periode konsisten dengan export; pengguna tanpa otorisasi tidak bisa mengekspor data pribadi; laporan wallet berbeda jelas dari laporan kas/bank travel.

### 51.6 Matriks implementasi dan UAT wajib

| ID | Fitur | Modul yang diselaraskan | Prioritas | UAT minimal |
|---|---|---|---|---|
| FT-01 | Invoice dan kuitansi otomatis | MOD-07, MOD-09, MOD-12 | P0 | UAT-FT01-A: booking terbitkan 1 invoice; UAT-FT01-B: DP verified terbitkan 1 kuitansi, tidak dobel saat retry |
| FT-02 | Portal jamaah dan dokumen | MOD-08, MOD-17 | P0 | UAT-FT02-A: upload–review–reject–reupload; UAT-FT02-B: akses silang jamaah/tenant ditolak |
| FT-03 | Pembayaran, manifest, keberangkatan | MOD-07, MOD-09, MOD-12, MOD-14 (inti) dan §26–§28 | P0 | UAT-FT03-A: manifest sinkron; UAT-FT03-B: readiness gate; UAT-FT03-C: DP memicu hanya 1 SaaS charge |
| FT-04 | Notifikasi otomatis | MOD-02, MOD-18 | P0 | UAT-FT04-A: notifikasi invoice/DP/reject dokumen/perubahan jadwal; UAT-FT04-B: retry dan dedupe |
| FT-05 | Laporan siap pakai | MOD-11, MOD-13, MOD-15 (ringkasan), §28 | P0 | UAT-FT05-A: filter dan ekspor identik; UAT-FT05-B: rekonsiliasi total dan pemisahan wallet |

**Definition of Done P0:** kelima fitur lolos seluruh UAT dan test keamanan multi-tenant; portal berfungsi di mobile web; dokumen terproteksi; invoice dan kuitansi diterbitkan tepat satu kali per event; report dapat digunakan tanpa ekspor manual yang diproses ulang; transparansi biaya pemakaian Rp50.000/jamaah setelah DP verified.

**Catatan prioritas dan istilah:** tabel cakupan lama yang menempatkan seluruh Portal Agen/Jamaah atau seluruh Notifikasi sebagai P1 kini dipecah: **Portal Jamaah P0; Portal Agen P1; notifikasi in-app+email P0; provider WhatsApp/SMS dan integrasi lanjutan P1**. Operasional keberangkatan dasar P0 sedangkan hotel/tiket/visa lanjutan P1. Ringkasan keuangan siap pakai P0 sedangkan buku besar dan neraca akuntansi formal P1.


---

## 52. FT-06 — Free Trial 30 Hari, Mode Demo Terisolasi [P0] — Keputusan Final v3.3

### 52.1 Keputusan produk dan hubungan dengan monetisasi

- **Free Trial wajib untuk tenant baru** selama **30 × 24 jam** dihitung sejak `trial_started_at` (timestamp UTC), ditampilkan dalam zona waktu tenant. Batas tanggal dan jam akhir eksplisit pada UI.
- **Maksimal 20 booking-jamaah dummy** per tenant trial, dihitung kumulatif sejak trial dimulai (menghapus data tidak memulihkan kuota).
- **Maksimal 3 pengguna internal aktif** termasuk owner; undangan tertunda yang diterima saat kuota penuh harus ditolak secara aman. Akses portal jamaah simulasi tidak dihitung ke kuota user internal.
- Fitur inti **invoice/kuitansi PDF, portal jamaah, upload dokumen dummy, pembayaran simulasi, manifest, jadwal keberangkatan, notifikasi demo, dan laporan siap pakai** dapat dievaluasi. Invoice dan kuitansi diberi watermark **DEMO — TIDAK SAH UNTUK TRANSAKSI**.
- **Biaya trial Rp0**, tanpa setup, biaya berulang, wallet deduction, transaksi pembayaran sebenarnya, atau koneksi payment gateway live. Simulasi DP **tidak pernah menghasilkan charge Rp50.000**.
- **Trial satu kali per badan usaha/tenant**, berlaku kebijakan anti-abuse dan pengecualian manual oleh Platform Super Admin yang tercatat audit. Pemeriksaan perusahaan tidak boleh membuka PII sensitif kepada pihak yang tidak berizin.
- Setelah 30 hari, tenant secara otomatis berstatus **Active** tanpa biaya bulanan; konfirmasi jamaah nyata yang DP-nya telah diverifikasi selanjutnya mengikuti **Rp50.000 per booking-jamaah**, didanai oleh **prepaid wallet**. Status aktif tidak berarti biaya otomatis dikenakan.

### 52.2 Lifecycle dan perilaku akhir trial

`Register → Email verified → Provisioning → Trial → Trial expired/Convert now → Active → (wallet funded) → DP verified → charged once per real booking-jamaah`.

- Trial otomatis mulai hanya setelah tenant siap digunakan; jangan kurangi durasi akibat kegagalan provisioning.
- Banner dashboard menampilkan waktu tersisa dan jumlah slot dummy/user, serta panduan aktivasi penggunaan nyata.
- Notifikasi ke owner dan admin utama pada **H-7, H-3, H-1**, dan saat berakhir; terapkan deduplikasi per event dan per tenant. Email dan in-app P0; WhatsApp opsional P1.
- Konversi manual lebih awal tersedia. Konversi sebelum 30 hari mengakhiri hak trial dan tidak dapat diulang sendiri oleh tenant.
- Saat konversi, mode produksi dibuat terpisah. **Data demo tidak otomatis berubah menjadi data nyata**, tidak masuk pembukuan, kapasitas keberangkatan produksi, piutang, manifest resmi, atau laporan operasional nyata.
- Owner dapat melihat ringkasan data demo pada area terpisah untuk sementara, menghapusnya secara terkontrol, atau mengunduh contoh non-sensitif menurut kebijakan retensi; aktivitas demo tidak ikut diekspor sebagai transaksi legal. Retensi demo default usulan **30 hari setelah konversi**, kemudian dihapus secara terjadwal dan diaudit; retensi final harus disetujui tim legal/privacy sebelum produksi.
- Apabila tenant belum top-up ketika trial selesai, tenant tetap bisa login, menyiapkan master data dan booking draft produksi. **Konfirmasi baru setelah DP terverifikasi berstatus `pending_charge` sampai saldo wallet mencukupi**, tanpa menahan atau menghilangkan pencatatan penerimaan DP jamaah. Konfirmasi jamaah yang telah aktif tidak dibekukan karena wallet kosong.
- Suspensi hanya mengikuti kebijakan keamanan/fraud/ToS, **bukan** karena habisnya trial atau tidak ada transaksi berbayar.

### 52.3 Isolasi demo vs produksi — keamanan dan kualitas data

- Model data memiliki `environment` (`demo` / `production`) atau tenant demo namespace tersendiri, dan API memaksa scope sesuai konteks; tidak boleh ada query agregasi atau referensi silang environment.
- Nomor invoice demo, kuitansi demo, manifest demo, nomor booking demo, dan bukti pembayaran simulasi memakai prefiks khusus `DEMO-` dan watermark jelas.
- Pembayaran trial adalah event simulasi terisolasi: **tidak** mengirim ke penyedia pembayaran, rekening bank, jurnal akuntansi produksi, webhook live, modul pajak, atau SaaS ledger.
- Notifikasi demo hanya ke alamat/email yang sudah diverifikasi dan diizinkan; dilarang mengirim blast ke data kontak acak atau kontak jamaah nyata dari data simulasi.
- Upload dokumen dummy tetap harus aman: validasi tipe/ukuran, malware scan, otorisasi akses, encryption-at-rest dan penghapusan sesuai retensi. UI menganjurkan penggunaan data sintetis dan melarang penyimpanan paspor/KTP asli untuk simulasi.
- Laporan demo diberi label dan tidak tergabung ke KPI atau laporan finance/usage platform produksi.

### 52.4 Fungsi platform dan parameter yang bisa dikonfigurasi

| Parameter | Default final | Kendali |
|---|---|---|
| `trial_duration_days` | 30 | Platform Super Admin; perubahan berlaku pada trial baru kecuali explicit override |
| `trial_dummy_booking_limit` | 20 kumulatif | Platform Super Admin |
| `trial_internal_user_limit` | 3 termasuk owner | Platform Super Admin |
| `trial_price` | Rp0 | Tetap untuk MVP |
| `trial_reminder_days` | 7, 3, 1 | Template/event konfigurasi |
| `trial_data_retention_days` | 30 pascakonversi (usulan) | Keputusan compliance final |
| `trial_reentry_allowed` | False | Hanya exception tersetujui |

Super Admin dapat melihat trial aktif, durasi, conversion funnel, alasan gagal onboarding, pemakaian kuota serta log perpanjangan/pencabutan. Super Admin boleh memberi extension dengan alasan, pemberi persetujuan, batas waktu dan audit; tindakan ini tidak membuat tagihan atau membuka data jamaah tenant secara otomatis.

### 52.5 Model data minimum

- `tenant_trial(id, tenant_id UNIQUE, status, started_at, ends_at, converted_at, expired_at, dummy_booking_count, settings_snapshot_json, created_at, updated_at)`.
- `tenant_trial_event(id, tenant_id, actor_id, event_type, reason, metadata_json, created_at)` — append-only untuk start, reminder, limit reached, extension, conversion, expiration.
- `trial_entitlement(tenant_id, internal_users_limit, dummy_booking_limit, enabled_modules_json)` — snapshot aturan saat trial dibuat; tidak bergantung pada paket subscription lama.
- `demo_data_record` atau penanda `environment` dan namespace penyimpanan demo; semua FK, unique constraint dan permission harus tenant-scoped serta environment-scoped.
- Job expiration dan reminder bersifat **idempotent**, aman saat dijalankan ulang atau paralel.

### 52.6 API minimum (ilustratif; endpoint final dalam Product Spec)

| Endpoint | Metode | Akses | Perilaku |
|---|---|---|---|
| `/api/v1/trial/status` | GET | Tenant owner/admin | Sisa waktu, limit, penggunaan, status |
| `/api/v1/trial/convert` | POST | Tenant owner | Konversi dini yang atomik; tidak menagih |
| `/api/v1/trial/demo-bookings` | POST | Admin travel trial | Create dummy booking jika di bawah kuota |
| `/api/v1/platform/trials` | GET | Super Admin | Ringkasan trial, filter status |
| `/api/v1/platform/trials/{id}/extend` | POST | Super Admin | Extension berbasis alasan dan audit |

### 52.7 Acceptance criteria / UAT wajib

| ID | Skenario | Hasil yang diharapkan |
|---|---|---|
| TR-01 | Signup tenant baru dan provision sukses | Trial aktif tepat 30 hari dari provisioning selesai |
| TR-02 | Membuat 20 booking dummy | Sukses; booking ke-21 ditolak dengan informasi kuota |
| TR-03 | Hapus satu booking dummy setelah limit tercapai | Kuota kumulatif tidak kembali; ke-21 tetap ditolak |
| TR-04 | Owner + 2 staf internal | Diizinkan; user internal ke-4 ditolak |
| TR-05 | Buat invoice, kuitansi, manifest dan laporan demo | Semua bertanda DEMO dan tidak masuk transaksi produksi |
| TR-06 | Simulasikan DP dalam trial | Wallet tidak dipotong; tidak muncul SaaS charge atau pembayaran sungguhan |
| TR-07 | Reminder H-7/H-3/H-1 diproses ulang | Satu pesan logis per trigger/kanal/penerima; audit tercatat |
| TR-08 | Trial habis, tenant belum top-up | Konversi ke Active gratis; tenant tidak disuspend |
| TR-09 | Booking nyata DP terverifikasi setelah konversi | Charge Rp50.000 persis sekali, jika saldo cukup; jika kurang pending_charge |
| TR-10 | Tenant memilih convert early | Status Active, tidak dapat memulai trial kedua secara mandiri |
| TR-11 | Jalankan expiration job berkali-kali/paralel | Tidak ada konversi duplikat, kerusakan data atau double charge |
| TR-12 | User tenant A meminta demo tenant B/production record | Akses ditolak pada API, file storage, laporan dan export |
| TR-13 | Data demo dihapus sesuai retensi | Production records tidak terdampak; audit penghapusan tersedia |
| TR-14 | Super Admin memperpanjang trial | Perlu alasan dan audit, tidak mengubah wallet/charge |
| TR-15 | Import / export laporan demo | Semua berlabel demo, data sensitif terlindungi, tidak bercampur laporan nyata |

**Definition of Done P0:** ketentuan trial pada §52 lulus TR-01 sampai TR-15, diuji dengan batas waktu yang dibekukan/time travel, aman untuk concurrency, memiliki metrik conversion, monitoring, audit log, perlindungan multi-tenant, dokumentasi API, dan tidak mengubah kebijakan inti SaaS **Rp50.000 per jamaah setelah verified DP**.

**Ketentuan prioritas:** §52 menggantikan semua referensi terdahulu yang menyebut trial opsional, trial tidak masuk MVP, trial berakhir menyebabkan `past_due`/suspend, atau trial sebagai langganan bulanan. Seluruh modul travel dan lima fitur operasional wajib pada §51 tetap berlaku.


## 53. Identitas Produk Umrovia & Peta Domain [P0/P1] — Berlaku Menggantikan Nama Produk Generik

### 53.1 Keputusan produk
- **Nama merek produk:** **Umrovia**. Nama produk pada label UI, email, template standar, help center, dan dokumen publik adalah Umrovia; nama travel tetap menonjol dalam konteks tenant.
- **Domain utama yang direncanakan:** `umrovia.com`, **bersyarat** pada verifikasi kepemilikan domain dan pemeriksaan merek. Belum mengklaim domain ini telah dibeli atau tersedia.
- **Positioning:** *Smart Umrah & Hajj Management*. Tagline pemasaran opsional: *Kelola Travel Lebih Mudah, Layani Jamaah Lebih Baik*.
- Penamaan tidak mengubah biaya: onboarding Rp0, trial 30 hari, 20 jamaah dummy, 3 pengguna internal trial, dan charging Rp50.000 per booking-jamaah nyata setelah DP terverifikasi.

### 53.2 Sistem permukaan digital (deployment targets)

| ID | Hostname | Tanggung jawab | Audiens | Fase |
|---|---|---|---|---|
| DOM-01 | `umrovia.com` (+ `www`) | Situs pemasaran, fitur, skema harga per jamaah, FAQ, kontak, daftar/login entry | Publik | P0 |
| DOM-02 | `app.umrovia.com` | Antarmuka workspace tenant, onboarding/trial, dashboard dan operasi travel; pemilihan tenant aman jika user multi-travel | Owner dan staf tenant | P0 |
| DOM-03 | `admin.umrovia.com` | Control plane SaaS: tenant, harga, wallet reconciliation, dukungan dan audit | Staf platform terotorisasi | P0 |
| DOM-04 | `api.umrovia.com` | REST API versi publik internal, auth, webhooks pada path terpisah, health dan dokumentasi terbatas | Web clients/integrasi | P0 |
| DOM-05 | `{slug}.umrovia.com` | Entry point vanity per travel, resolver tenant dari host, halaman tenant-branded jika enabled | Pengguna tenant/jamaah sesuai izin | P1 |

**Klarifikasi:** `www.umrovia.com` redirect ke canonical `umrovia.com`; penggunaan `api.umrovia.com` tidak bermakna API boleh diakses tanpa autentikasi. Domain dan subdomain yang didaftarkan di tabel adalah alamat *rencana*.

### 53.3 Alur pengguna dan prioritas
1. Pengunjung dari situs publik masuk ke registrasi, memverifikasi email, dan mendapatkan workspace trial melalui `app.umrovia.com` (P0).
2. Owner/travel mengakses aplikasi di `app.umrovia.com`; workspace aktif dipilih melalui tenant membership yang disahkan server, **tidak** hanya dari query parameter (P0).
3. Platform Super Admin masuk lewat `admin.umrovia.com` dengan autentikasi terpisah dan MFA (P0).
4. Permintaan aplikasi menuju `api.umrovia.com`; semua endpoint privat wajib memeriksa identitas, tenant context, role dan izin baris data (P0).
5. Saat P1, `travelcontoh.umrovia.com` membawa user ke workspace tenant yang sesuai, dengan aturan URL yang tidak mengekspos data antar-tenant.

### 53.4 Persyaratan produk lintas domain
- P0: desain responsif, identitas visual konsisten, favicon/logo Umrovia, SEO dan sitemap hanya untuk website publik, halaman legal, kebijakan privasi, S&K, contact/support, status maintenance.
- P0: private app/admin **tidak diindeks mesin pencari**; komunikasi HTTPS; anti-phishing domain canonical, redirect aman dan cookie policy yang dirancang untuk host terpisah.
- P0: keamanan login, verifikasi email, password reset, logout, session expiry, MFA admin, audit login; larang transfer token via URL terbuka.
- P1: slug tenant unik global, reserved hostname (`www`, `app`, `api`, `admin`, dll.) diblokir; rename slug dan riwayat redirect dikelola; wildcard DNS/TLS serta host allowlist.
- P1: domain kustom tenant merupakan fitur **terpisah**, tidak otomatis masuk cakupan `{slug}.umrovia.com`.

### 53.5 Acceptance criteria
| ID | Skenario | Hasil |
|---|---|---|
| BR-01 | Pengunjung mengakses `umrovia.com`/`www` | Website publik tampil; `www` redirect aman ke canonical |
| BR-02 | User tenant berhasil login | Masuk ke `app.umrovia.com` dengan workspace tenant yang sah |
| BR-03 | User tenant mengakses `admin.umrovia.com` | Ditolak; endpoint admin juga menolak di server |
| BR-04 | Super Admin login tanpa MFA | Akses control plane gagal sampai MFA terpenuhi |
| BR-05 | Request API dengan tenant ID/host dimanipulasi | Ditolak; data tenant lain tidak pernah dikembalikan |
| BR-06 | Perubahan branding Umrovia | Konsisten pada publik, aplikasi, notifikasi dan PDF template standar |
| BR-07 | Akses host tidak dikenal | Ditolak (bukan fallback ke tenant lain) |
| BR-08 (P1) | Tenant membuat slug reserved/duplikat | Ditolak dengan pesan validasi |
| BR-09 (P1) | Akses `{slug}.umrovia.com` | Hanya menampilkan tenant sesuai mapping terpercaya, TLS valid |

**Ketentuan prioritas:** §53 merupakan sumber kebenaran untuk nama brand, hostname dan fase delivery; apabila sitemap atau host lama pada bagian terdahulu bertentangan, §53 berlaku. Penerapan produksi tetap memerlukan akuisisi domain dan pemeriksaan merek terlebih dahulu.


---

## 54. Roadmap Pengembangan Resmi Umrovia (Revisi PRD v3.5)

### 54.1 Tujuan dan batasan
Roadmap ini mengurutkan seluruh kemampuan MVP pada PRD berdasarkan dependensi bisnis dan risiko. **Estimasi awal 19 minggu untuk satu developer** merupakan *planning baseline*, bukan tenggat tetap, dan belum memasukkan buffer eksternal (persetujuan gateway, registrasi domain, legal, migrasi data klien). Detail task harian dan progres diatur pada `DEVELOPMENT_ROADMAP.md` agar PRD tidak harus direvisi untuk setiap perubahan sprint.

**Rencana MVP tidak mengubah keputusan produk:** brand `Umrovia`; domain P0 `umrovia.com`, `app.umrovia.com`, `admin.umrovia.com`, `api.umrovia.com`; vanity subdomain P1; trial 30×24 jam/20 jamaah dummy/3 pengguna internal; biaya setup dan bulanan Rp0; charging Rp50.000 **sekali per booking-jamaah nyata setelah DP sah terverifikasi**; prepaid wallet, tanpa mengalihkan dana DP jamaah ke operator SaaS.

### 54.2 Fase dan milestone
| Fase | Fokus | Durasi estimasi | Deliverable / exit gate | Prioritas |
|---|---|---:|---|---|
| F01 | Fondasi proyek | 1 minggu | Aplikasi dan API bootstrapped secara lokal; CI lint/test berjalan; migrasi baseline berhasil | P0 |
| F02 | Authentication dan Multi-Tenancy | 2 minggu | Dua tenant tidak dapat membaca/mengubah data satu sama lain; login/reset/logout berfungsi | P0 |
| F03 | Free Trial | 1 minggu | Trial berakhir tanpa tagihan; konversi Active tidak memigrasikan transaksi DEMO ke produksi | P0 |
| F04 | Dashboard & pengaturan travel | 2 minggu | Tenant owner mengelola staf dan profil dengan audit; user tanpa izin ditolak | P0 |
| F05 | Operasional inti travel | 4 minggu | Pendaftaran jamaah berhasil; seat count aman dari overbooking; manifest dapat dibuat | P0 |
| F06 | Pembayaran jamaah & SaaS Wallet | 3 minggu | DP terverifikasi memicu tepat satu debit; saldo tidak cukup menghasilkan pending_charge; ledger rekonsiliasi | P0 |
| F07 | Portal, manifest & notifikasi | 3 minggu | Jamaah hanya mengakses datanya; upload aman; email berbasis event dikirim terpantau | P0 |
| F08 | Laporan, Platform Admin & hardening | 3 minggu | Laporan rekonsiliasi akurat; akses admin terpisah/MFA; backup-restore diuji; pilot layak go-live | P0 |

**Total fase berurutan: 1 + 2 + 1 + 2 + 4 + 3 + 3 + 3 = 19 minggu.** Angka tersebut estimasi effort kalender apabila fokus full-time; QA, perbaikan dan dependensi integrasi mungkin menyebabkan perubahan.

### 54.3 Milestone, nilai bisnis, dan prioritas
| Milestone | Target hasil yang dapat didemonstrasikan | Penerimaan bisnis |
|---|---|---|
| M1 (akhir F02) | Pendaftaran, login, tenant workspace end-to-end | Owner tenant A tidak bisa melihat data tenant B dalam UI, API, maupun query DB di bawah konteks tenant |
| M2 (akhir F04) | Tenant trial onboarding dan pengaturan travel | Trial bisa dipakai tanpa pembayaran, data demo tidak tercampur transaksi riil |
| M3 (akhir F05) | Booking jamaah hingga manifest dasar | Seat tidak melebihi kapasitas; admin dapat menjalankan perjalanan dasar |
| M4 (akhir F06) | DP → verifikasi → wallet debit → invoice/kuitansi | Pungutan tepat sekali dan tercatat di ledger; saldo kurang tidak menghilangkan DP jamaah |
| M5 (akhir F08) | Portal jamaah, notifikasi, laporan, admin platform, keamanan | UAT lintas tenant dan rekonsiliasi lolos, backup/restore terbukti, pilot siap |

### 54.4 Critical path dan urutan keputusan
1. Tenant isolation, identitas dan RBAC wajib stabil **sebelum** menyimpan data travel/jamaah nyata.
2. Trial demo menggunakan penanda environment/dataset dan larangan charging nyata; tidak boleh mengubah ledger produksi.
3. Booking dan status pembayaran harus terdokumentasi sebelum implementasi peristiwa `DP_VERIFIED` yang memicu billing SaaS.
4. Wallet ledger dan engine idempotent harus siap sebelum top-up/payment gateway produksi diaktifkan.
5. Portal jamaah, invoice dan manifest harus memakai otorisasi object-level dan tenant context yang sama.
6. Admin platform **bukan** superuser otomatis atas PII jamaah; support access menggunakan approval, masking dan audit.
7. Domain publik P0 disiapkan untuk delivery; wildcard dan domain milik tenant ditunda P1/P2.

### 54.5 Scope control dan release policy
- **P0:** seluruh fitur wajib pada §51–§53, termasuk invoice/kuitansi otomatis, portal dokumen jamaah, manifest/keberangkatan, notifikasi penting serta laporan operasional dan keuangan siap pakai.
- **P1:** vanity tenant subdomain, WhatsApp berbayar, rooming/visa lanjutan, enterprise postpaid, akuntansi kompleks dan diskon volume jika disetujui.
- **P2:** custom domain milik tenant, integrasi enterprise tambahan.
- Sprint hanya dapat dinyatakan selesai jika code review, test otomatis, audit akses, migrasi yang dapat diulang, dokumentasi endpoint dan demo acceptance diselesaikan.
- Penyesuaian estimasi dan assignment dicatat pada `DEVELOPMENT_ROADMAP.md`; perubahan fitur/aturan bisnis harus direfleksikan ke PRD dan Product Spec.

### 54.6 Acceptance roadmap
| ID | Validasi | Kriteria lulus |
|---|---|---|
| RM-01 | Milestone fase | Setiap fase memiliki owner, deliverables, dependency, acceptance, dan status di roadmap |
| RM-02 | Single-tenant escape test | Upaya membaca resource tenant lain ditolak pada API & DB |
| RM-03 | Free trial | Berakhir tanpa langganan/tagihan otomatis dan tanpa data demo keuangan produksi |
| RM-04 | Pay-per-jamaah | Satu booking-jamaah yang DP-nya verified tidak didebit lebih dari sekali meski webhook diulang |
| RM-05 | Nilai tenant | Invoice, portal jamaah, manifest, notifikasi, laporan dapat didemokan sebelum pilot go-live |
| RM-06 | Operational readiness | Health check, monitoring, audit, restore test, dokumentasi deploy/rollback tersedia |

**Presedensi:** §54 mengatur urutan dan milestone; §52 mengatur trial; §50 dan §42–§49 mengatur monetisasi; §51 fitur operasional wajib; §53 brand/domain. Timeline tidak dapat digunakan untuk meniadakan persyaratan P0.
