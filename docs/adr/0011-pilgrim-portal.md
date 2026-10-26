# ADR-0011 — Portal jamaah: undangan, object-level permission dan dokumen privat

Tanggal: 26 Oktober 2026. Status: accepted. Sprint S14 (Roadmap §3: "Jamaah
portal, auth, profile/doc upload"; gate "Object-level permissions").
Product Spec §3 (Jamaah: booking milik sendiri), §7.6, §8.4, §10, UI-13,
POR01/POR02, SEC02.

## Akun dan undangan

- Staf (`pilgrims.write`) mengirim undangan dari detail jamaah. Token
  `<tenant_id>.<acak 32 byte>` dikirim lewat email; hanya SHA-256 disimpan di
  `portal_portalinvite` (RLS ENABLE+FORCE). Berlaku `PORTAL_INVITE_TTL_DAYS`
  (7), sekali pakai; undangan baru mencabut undangan terbuka sebelumnya.
- Bagian tenant pada token hanya memilih konteks RLS; keabsahan tetap
  ditentukan hash. Inspeksi publik menampilkan email tersamar.
- Email tanpa akun: menerima undangan sekaligus membuat akun ACTIVE dan
  terverifikasi (kepemilikan email dibuktikan oleh tautan) dengan validasi
  password Django, lalu login. Email yang sudah punya akun wajib login sebagai
  email tersebut (`login_required`) — mencegah pengambilalihan akun.
- Akun portal tidak memiliki membership tenant, sehingga tidak dihitung
  sebagai pengguna internal trial (TR04) dan tidak dapat memakai dashboard
  staf (shell mengarahkan ke `/portal`). `next` login hanya menerima path
  `/portal…`.

## Object-level permission

`portal_portalaccess` (tabel platform berisi ID saja: user, tenant, pilgrim,
environment, status) menghubungkan akun ke jamaah. Request portal tidak
membawa membership, sehingga setiap endpoint:

1. mengambil grant ACTIVE milik `request.user` (selain itu 404),
2. masuk ke konteks RLS tenant grant (`platform_tenant_context`),
3. menyaring setiap query ke `pilgrim_id` grant.

Booking grup hanya menampilkan peserta milik sendiri: nominal baris invoice
sendiri, alokasi terverifikasi sendiri, dan kuitansi untuk pembayaran yang
dialokasikan kepadanya. PDF invoice/kuitansi hanya tersedia bila seluruh
isinya milik jamaah tersebut, karena dokumen grup memuat nama jamaah lain
(POR02). Draf/kedaluwarsa tidak ditampilkan. Staf dapat mencabut grant atau
undangan; pencabutan berlaku seketika, termasuk untuk tautan unduh yang masih
berlaku.

## Dokumen

- Unggah multipart oleh jamaah (portal) atau staf. Allowlist PDF/JPEG/PNG
  ditentukan dari magic bytes (nama/MIME klien diabaikan), maksimal
  `PILGRIM_DOCUMENT_MAX_MB` (10). PDF berisi `/JavaScript`, `/JS`, `/Launch`,
  `/EmbeddedFile`, `/RichMedia` atau `/XFA` ditolak.
- Berkas disimpan privat di storage default dengan kunci
  `tenants/{t}/environments/{e}/pilgrims/{p}/{kind}/{uuid}.{ext}`; tidak ada
  route media publik. Produksi dapat mengganti `STORAGES["default"]` ke bucket
  S3 privat tanpa perubahan kode.
- Setiap unggahan adalah versi baru `UPLOADED` yang menunggu review; versi
  lama dan alasan penolakan tetap terlihat (POR01). Dokumen yang sudah
  APPROVED tidak dapat diganti dari portal.
- Unduh lewat path bertanda tangan Django (`TimestampSigner`) berisi tenant,
  dokumen, user dan cakupan (`portal`/`staff`); kedaluwarsa
  `SIGNED_URL_TTL_SECONDS` (600) → 403 (SEC02). Saat diunduh, pemilik sesi
  harus sama dengan user dalam token dan izinnya dicek ulang (grant aktif,
  atau membership dengan `pilgrims.read`). Respons `attachment`, `no-store`,
  `nosniff`, CSP sandbox. Setiap unggah/unduh tercatat di audit.

## Profil

Jamaah hanya dapat mengoreksi kontak (telepon, email, alamat, kontak darurat).
Nama, NIK dan paspor tetap dikoreksi travel.

## Di luar cakupan

Pemindai antimalware (ClamAV atau layanan setara) belum tersedia; mitigasi
sementara adalah allowlist magic bytes, penolakan PDF aktif, unduhan sebagai
attachment dan review petugas. Kotak masuk notifikasi portal dan email
berbasis event → S16. Presign langsung ke bucket S3 → saat object storage
produksi dipilih. Akses keluarga/wali untuk beberapa jamaah sudah didukung
model (beberapa grant per akun) tetapi alurnya belum dirancang khusus.
