# Runbook — Backup & restore

Target pilot (Spec §13): RPO ≤ 24 jam, RTO ≤ 8 jam; drill restore bulanan.
Drill S19 pada data uji 7.812 baris: restore + verifikasi 10 detik.

## Backup harian

- Skrip: `infra/backup/backup.sh` — `pg_dump -Fc` (termasuk RLS & policy) +
  arsip media (dokumen jamaah) + SHA-256, dienkripsi AES-256 (PBKDF2).
- Jadwal: cron/systemd timer harian, misalnya 01:00 WIB:
  `BACKUP_SOURCE=compose BACKUP_PASSPHRASE=… BACKUP_DIR=/srv/backups infra/backup/backup.sh`
  (produksi: `DATABASE_URL` + `MEDIA_DIR`).
- `BACKUP_PASSPHRASE` disimpan di secret manager, terpisah dari server
  backup. Tanpa passphrase, backup tidak dapat dibuka.
- Salin `BACKUP_DIR` ke penyimpanan objek privat di region/akun berbeda
  (versioning + retensi; jangan publik). Retensi lokal bawaan 14 hari.
- PITR (WAL archiving) dianjurkan bila memakai Postgres terkelola.

## Drill restore bulanan (wajib)

```
BACKUP_PASSPHRASE=… ADMIN_DATABASE_URL=postgres://admin@host:5432/postgres \
SOURCE_DATABASE_URL=postgres://…/umrovia REPORT=/srv/backups/drill-$(date +%F).json \
infra/backup/restore_drill.sh /srv/backups/umrovia-<stamp>.tar.enc
```

Skrip memverifikasi checksum, me-restore ke database **baru** (tidak pernah
menimpa produksi), memastikan tidak ada migrasi tertunda, menjalankan
`verify_integrity` (RLS semua tabel tenant, ledger, invoice, checksum PDF, kursi,
antrean) dan membandingkan jumlah baris dengan sumber, lalu menghapus database
drill. Simpan laporan JSON sebagai bukti audit. Gagal → insiden S2.

**Produksi VPS** (tanpa klien Postgres di host): drill di laptop, dengan arsip
yang diambil dari **bucket offsite** — yang diuji adalah salinan yang tersisa bila
VPS hilang — dan passphrase dari password manager (bukan dari VPS):

```
STAMP=20261028T180003Z   # pilih dari: ssh umrovia-prod rclone lsl neo:umrovia-backups
ssh umrovia-prod "T=\$(mktemp -d); rclone copy neo:umrovia-backups \$T --include 'umrovia-$STAMP.tar.enc*'; \
  cd \$T && tar cf - umrovia-$STAMP.tar.enc*; rm -rf \$T" | tar xf - -C ~/drill
read -rsp "Passphrase: " BACKUP_PASSPHRASE; export BACKUP_PASSPHRASE
ADMIN_DATABASE_URL=postgres://$USER@localhost:5432/postgres REPORT=~/drill/drill-$(date +%F).json \
  infra/backup/restore_drill.sh ~/drill/umrovia-$STAMP.tar.enc
ssh umrovia-prod "umask 077; cat > /srv/backups/drill-$(date +%F).json" < ~/drill/drill-$(date +%F).json
rm ~/drill/umrovia-$STAMP.tar.enc*; unset BACKUP_PASSPHRASE
```

Hitungan baris tidak dibandingkan (database produksi tidak terbuka ke luar dan
sudah berubah sejak backup); pastikan saja jumlahnya wajar terhadap
`docker compose exec api python manage.py verify_integrity` di VPS.

| Tanggal | Arsip | Hasil | Durasi |
|---|---|---|---|
| 2026-10-29 | umrovia-20261028T180003Z (dari bucket NEO) | OK — RLS 48/48, 6/6 cek | 9 detik |

## Restore sungguhan (bencana)

1. Hentikan penulisan: `docker compose stop worker web api` (atau mode maintenance).
2. Pilih backup terakhir yang lolos drill; jalankan drill dengan `KEEP=1` ke
   database baru `umrovia_restored`.
3. Arahkan `DATABASE_URL` ke database hasil restore; pulihkan media dari
   `media.tgz` ke volume media.
4. Start `api` (migrasi berjalan), lalu `worker`, `web`. Jalankan
   `infra/deploy/smoke.sh`, `verify_integrity`, `reconcile_wallets`.
5. Data setelah titik backup hilang (RPO): umumkan ke travel; transaksi
   gateway Midtrans di rentang itu direkonsiliasi ulang dari dashboard
   Midtrans (top-up akan tersinkron lewat `reconcile_wallets`).
