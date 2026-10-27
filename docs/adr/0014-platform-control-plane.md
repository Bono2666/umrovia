# ADR-0014 — Konsol platform: peran staf, MFA, lifecycle tenant dan dukungan

Tanggal: 27 Oktober 2026. Status: accepted. Sprint S18 (Roadmap §3: "Platform
control plane, tenant lifecycle, support"; gate "Admin MFA/audit, no PII
leakage"). Product Spec §3, §6.1, §8.5, §13, §18.1–18.2, UI-18/19.

## Peran dan otorisasi

Staf platform adalah akun `is_staff`, aktif dan terverifikasi, dengan izin
Django dari grup (migrasi `platform.0003`):

| Grup | Izin |
|---|---|
| Platform Super Admin | `console_view`, `tenant_manage`, `pricing_manage`, `audit_view`, `support_manage` |
| Platform Billing | `console_view`, `wallet.settle_topup`, `billing.approve_adjustment` |
| Platform Support | `console_view`, `support_manage` |

Role tenant, termasuk Owner `*`, tidak pernah memberi izin platform. Setiap
endpoint `/api/v1/platform/*` memeriksa di server (`PlatformPermission`):
staf + izin + **MFA segar**. Ini termasuk endpoint settle top-up dan refund
dari S12/S13. Hostname `admin.umrovia.com` bukan otorisasi; konsol dilayani di
`/platform` pada build yang sama. Akun dibuat lewat `create_platform_staff`
(satu peran) atau `createsuperuser`; disarankan akun terpisah dari akun travel.
Django admin tidak di-route.

## MFA (TOTP)

RFC 6238 (SHA-1, 6 digit, 30 detik, toleransi ±1 langkah), diimplementasikan
tanpa dependensi baru dan diuji dengan vektor RFC. Secret dienkripsi Fernet
(kunci PII); langkah terakhir yang dipakai disimpan sehingga kode yang sama
tidak dapat dipakai ulang. Pendaftaran meminta ulang password; 10 kode
pemulihan sekali pakai disimpan sebagai SHA-256 dan ditampilkan sekali.
Verifikasi menandai sesi (`cycle_key`, berlaku `PLATFORM_MFA_TTL_SECONDS`,
bawaan 8 jam) dan dibatasi 10/menit. Keberhasilan dan kegagalan dicatat di
audit, di luar blok transaksi agar kegagalan tidak ikut ter-rollback.
Perangkat yang aktif tidak dapat ditimpa sendiri; reset dilakukan operator
lewat `reset_platform_mfa <email> --reason` (beraudit).

## Batas data ("no PII leakage")

Konsol hanya mengembalikan metadata usaha tenant, status, kuota, hitungan dan
agregat uang. Tidak ada nama, kontak, NIK, paspor maupun dokumen jamaah.
Email pengguna travel selalu tersamar. Audit platform hanya menampilkan
kunci `changes` dari allowlist; teks bebas dari travel tidak ditampilkan,
alasan yang ditulis staf platform boleh tampil. Membuka detail tenant
dicatat (`platform.tenant.viewed`). Test otomatis memastikan delapan respons
konsol tidak memuat nama, NIK, email maupun telepon jamaah, juga email owner
lengkap.

Agregat lintas tenant (ringkasan, antrean billing, pemakaian per tenant)
dihitung dengan masuk ke konteks RLS tiap tenant (`platform_tenant_context`).
Cara ini memadai untuk skala pilot; agregat terjadwal menyusul bila jumlah
tenant besar.

## Lifecycle tenant

- **Suspend** (`tenant_manage`, alasan ≥ 10 karakter): dari TRIAL, ACTIVE atau
  RESTRICTED; status sebelumnya disimpan. Middleware tenant menolak semua API
  operasional dengan `403 tenant_suspended`. Yang tetap terbuka: akun,
  pemilihan workspace dan tiket Bantuan. Grant portal jamaah travel tersebut
  ikut tertutup. Data tidak diubah.
- **Reactivate**: memulihkan status sebelumnya. Tidak bisa selama ada
  pengajuan pengakhiran terbuka.
- **Terminate**: dua orang. Satu admin mengajukan (tenant harus ditangguhkan),
  admin lain memutuskan; pengaju tidak dapat memutuskan sendiri. TERMINATED
  final dari konsol; data tidak dihapus (penghapusan/ekspor mengikuti
  prosedur hukum terpisah).
- Konversi/expiry trial tidak lagi mencabut suspend: statusnya tetap
  SUSPENDED dan status yang akan dipulihkan menjadi ACTIVE.
- Trial dapat diperpanjang 1–30 hari per pengajuan (beralasan, event trial
  EXTENDED + audit).

## Tarif

Versi tarif hanya bisa dijadwalkan ke depan (≥ 1 jam), dengan kode unik dan
alasan. Versi lama dan charge yang sudah dibuat tidak berubah (charge
menyimpan versi tarifnya).

## Dukungan

`SupportTicket`/`SupportMessage` adalah tabel platform (bukan RLS). Travel
hanya melihat tiketnya sendiri (filter server-side per workspace aktif); semua
anggota aktif boleh membuka dan membalas tiket. Staf Support melihat isi tiket
dan diagnosis (metadata + hitungan), tanpa akses data operasional travel. Akses
dukungan sementara ke data tenant (time-bound elevation dengan persetujuan
travel) belum disediakan, sehingga support tidak pernah membaca data jamaah.
Catatan internal tidak pernah dikirim ke travel. Balasan platform mengantrekan
email ke pembuka tiket (template `support.replied`, S16).

## Di luar cakupan

Elevasi akses support beraudit, WebAuthn/passkey, MFA untuk role keuangan
tenant, QR code pendaftaran (kunci ditampilkan untuk dimasukkan manual atau
tautan `otpauth://`), dan host `admin.umrovia.com` terpisah saat deploy (S19).
