# Runbook — Deploy pertama ke VPS (Biznet Gio NEO Lite, Ubuntu 24.04)

Untuk: operator yang memasang Umrovia produksi pertama kali di satu VPS.
Stack: `docker-compose.staging.yml` (setting **produksi**, di belakang Caddy +
Let's Encrypt) dengan secret produksi di `.env.production`.
Domain `umrovia.com` (NEO DNS), VPS `103.87.66.228`, user `bono2666`.

Estimasi waktu: 60–90 menit (build pertama 5–15 menit).

## 0. Prasyarat

| Butir | Cek |
|---|---|
| VPS NEO Lite MM 8.4, Ubuntu 24.04 LTS | IP publik diketahui |
| DNS: record **A** `@`, `app`, `admin`, `api` → `103.87.66.228`, `www` → CNAME | Lihat "Record DNS" di bawah |
| Security Group Biznet Gio: inbound TCP 22, 80, 443 | Port 80 wajib terbuka untuk penerbitan sertifikat |
| Kunci SSH `umrovia.pem` dan user `bono2666` | Bagian 1 |
| Akun SMTP email transaksional (host, port, user, password) | Untuk verifikasi email & notifikasi |
| Akses baca repo `github.com/Bono2666/umrovia` | Bagian 3 (deploy key) |
| Password manager untuk menyimpan secret | Bagian 4 & 8 |

### Record DNS (portal Biznet Gio → NEO DNS → zona `umrovia.com`)

| Nama | Tipe | Nilai | TTL |
|---|---|---|---|
| `@` (umrovia.com — situs marketing) | A | `103.87.66.228` | 300 |
| `www` | CNAME | `umrovia.com.` | 300 |
| `app` | A | `103.87.66.228` | 300 |
| `admin` | A | `103.87.66.228` | 300 |
| `api` | A | `103.87.66.228` | 300 |

Cek dari laptop (semuanya harus berujung di `103.87.66.228`):

```bash
for h in umrovia.com www.umrovia.com app.umrovia.com admin.umrovia.com api.umrovia.com; do echo "$h: $(dig +short @satu.neodns.id $h | tr '\n' ' ')"; done
```

### Record email

Email keluar aplikasi lewat **Brevo** (SMTP relay); email masuk `@umrovia.com` (mis. `halo@`,
penerima formulir kontak) lewat **Zoho Mail**. Nilai kode/kunci diambil dari dashboard masing-masing.

| Nama | Tipe | Nilai | Untuk |
|---|---|---|---|
| `@` | TXT | `brevo-code:…` | verifikasi domain Brevo |
| `brevo1._domainkey`, `brevo2._domainkey` | CNAME | dari Brevo | DKIM Brevo |
| `_dmarc` | TXT | `v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com` | DMARC |
| `@` | TXT | `zoho-verification=…` | verifikasi domain Zoho |
| `@` | MX | `mx.zoho.com` (10), `mx2.zoho.com` (20), `mx3.zoho.com` (50) | email masuk |
| `@` | TXT | `v=spf1 include:zohomail.com ~all` | SPF |

Di form NEO DNS: Name domain utama ditulis `@`, dan nilai MX **tanpa** titik di akhir (dengan titik
ditolak "Failed to add DNS record"). Setelah menambah record, cek bahwa versi zona naik dan record
terpublikasi (`dig +short MX umrovia.com @satu.neodns.id`); bila tidak, tambahkan ulang atau hubungi
Support Biznet Gio.

Domain utama `umrovia.com` dan `www` (saat ini CNAME ke `umrovia.com`) belum dilayani
stack ini; halaman marketing ada di host `app`. Bila ingin `umrovia.com` ikut aktif,
arahkan juga ke IP VPS lalu tambahkan blok pengalihan di `infra/deploy/Caddyfile`.

## 1. Kunci SSH di laptop (macOS)

SSH menolak kunci yang bisa dibaca user lain, jadi pindahkan dan kunci izinnya:

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
mv ~/Downloads/umrovia.pem ~/.ssh/umrovia.pem
chmod 600 ~/.ssh/umrovia.pem
cat >> ~/.ssh/config <<'EOF'

Host umrovia-prod
  HostName 103.87.66.228
  User bono2666
  IdentityFile ~/.ssh/umrovia.pem
  IdentitiesOnly yes
  ServerAliveInterval 30
EOF
ssh umrovia-prod 'hostname; lsb_release -ds; sudo -n true 2>/dev/null && echo sudo-tanpa-password || echo sudo-pakai-password'
```

Bila VPS baru hanya bisa dimasuki sebagai `root` (atau user bawaan lain), ganti
`User` di atas sementara, lalu jalankan bootstrap dengan `DEPLOY_USER=bono2666`.

## 2. Bootstrap server (langkah 1–6)

```bash
# dari folder repo di laptop
scp infra/deploy/bootstrap-ubuntu.sh umrovia-prod:~/
ssh umrovia-prod
sudo DEPLOY_USER=bono2666 bash ~/bootstrap-ubuntu.sh
```

Skrip ini: login SSH hanya dengan kunci (password & root dimatikan), ufw
(22/80/443), patch keamanan otomatis + fail2ban, Docker Engine + Compose dari
docker.com, swap 2 GB, zona waktu UTC + NTP, serta folder `/srv/umrovia`,
`/srv/backups`, `/etc/umrovia`. Aman dijalankan ulang. Log: `/var/log/umrovia-bootstrap.log`.

**Jangan tutup sesi itu dulu.** Di terminal laptop yang baru:

```bash
ssh umrovia-prod 'id; docker ps && echo docker-ok'
```

Berhasil → tutup sesi lama. Bila skrip menyebut reboot diperlukan: `ssh umrovia-prod 'sudo reboot'`,
tunggu 1 menit, login lagi.

## 3. Ambil kode

Repo `Bono2666/umrovia` saat ini **publik**, jadi cukup:

```bash
git clone https://github.com/Bono2666/umrovia.git /srv/umrovia
```

Bila repo dijadikan privat, pakai deploy key read-only. Di VPS:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N "" -C "umrovia-prod"
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/github_deploy
  IdentitiesOnly yes
EOF
cat ~/.ssh/github_deploy.pub
```

Tempel isi public key di GitHub → repo `umrovia` → Settings → Deploy keys →
Add deploy key (**tanpa** centang "Allow write access"). Lalu:

```bash
git clone git@github.com:Bono2666/umrovia.git /srv/umrovia
cd /srv/umrovia && git log --oneline -1
```

## 4. Konfigurasi produksi

```bash
cd /srv/umrovia
cp infra/deploy/production.env.example .env.production
chmod 600 .env.production
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" .env.production
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$(openssl rand -base64 48 | tr -d '\n')|" .env.production
sed -i "s|^PII_ENCRYPTION_KEY=.*|PII_ENCRYPTION_KEY=$(openssl rand -base64 32 | tr '+/' '-_')|" .env.production
nano .env.production   # isi CADDY_TLS (email operator), SMTP, CONTACT_RECIPIENT_EMAIL, rekening top-up manual
```

- **Simpan `POSTGRES_PASSWORD`, `SECRET_KEY` dan `PII_ENCRYPTION_KEY` di password
  manager sekarang.** Kehilangan `PII_ENCRYPTION_KEY` = NIK/paspor jamaah tidak
  bisa dibaca, termasuk dari backup.
- Jangan pernah mengubah `PII_ENCRYPTION_KEY` setelah data jamaah masuk.
- Nama file compose `docker-compose.staging.yml`, tetapi isinya setting produksi
  (`config.settings.production`). Midtrans bawaan mode **sandbox**; mode produksi hanya
  bila `.env.production` mengisi `MIDTRANS_IS_PRODUCTION=True` (bagian "Midtrans produksi").

Agar perintah `docker compose` di folder ini otomatis memakai stack produksi:

```bash
cat >> ~/.profile <<'EOF'
export COMPOSE_FILE=docker-compose.staging.yml
export COMPOSE_PROJECT_NAME=umrovia
export COMPOSE_ENV_FILES=.env.production
EOF
source ~/.profile
```

## 5. Build & jalankan

```bash
cd /srv/umrovia
docker compose up -d --build
docker compose ps                       # db, redis, api, worker sehat; web & proxy jalan
docker compose logs -f proxy            # tunggu "certificate obtained successfully" untuk 3 host
```

Container `api` menjalankan migrasi database otomatis saat start; `worker`
menunggu `api` sehat.

## 6. Verifikasi

```bash
cd /srv/umrovia
SITE_HOST=umrovia.com APP_HOST=app.umrovia.com ADMIN_HOST=admin.umrovia.com API_HOST=api.umrovia.com \
  PORT=443 HTTP_PORT=80 infra/deploy/smoke.sh
docker compose exec api python manage.py verify_integrity
```

Hasil yang diharapkan: `smoke: 20 lulus, 0 gagal` dan `verify_integrity` OK.
Lalu buka `https://umrovia.com` dan `https://app.umrovia.com/login` di browser (gembok valid,
tanpa peringatan).

Pembagian host: `umrovia.com` hanya melayani halaman marketing (`/`, `/pricing`, `/kontak`,
`/kebijakan-privasi`); rute lain dialihkan ke `app.umrovia.com`. `www` dialihkan ke domain utama.
`app.umrovia.com/` menuju `/login` dan halaman marketing di host app dialihkan ke `umrovia.com`.

## 7. Akun pertama

**Staf platform** (konsol `https://admin.umrovia.com`), pakai email terpisah
dari akun travel:

```bash
docker compose exec api python manage.py create_platform_staff ops@umrovia.com \
  --role "Platform Super Admin" --name "Nama Anda"
```

Password diminta (minimal 12 karakter). Login di host admin, lalu daftarkan MFA.

**Travel pertama**: daftar di `https://app.umrovia.com/register` → verifikasi
email (memastikan SMTP bekerja) → Owner travel masuk ke Ringkasan.

## 8. Backup harian + salinan offsite

Buat file secret backup (sekali):

```bash
cat > /etc/umrovia/backup.env <<EOF
BACKUP_PASSPHRASE=$(openssl rand -base64 32 | tr -d '\n')
BACKUP_SOURCE=compose
BACKUP_DIR=/srv/backups
COMPOSE_FILE=docker-compose.staging.yml
COMPOSE_PROJECT_NAME=umrovia
COMPOSE_ENV_FILES=/srv/umrovia/.env.production
EOF
chmod 600 /etc/umrovia/backup.env
grep BACKUP_PASSPHRASE /etc/umrovia/backup.env   # salin ke password manager
```

Tanpa `BACKUP_PASSPHRASE`, backup tidak bisa dibuka. Uji sekali secara manual:

```bash
cd /srv/umrovia && (set -a; . /etc/umrovia/backup.env; set +a; infra/backup/backup.sh)
ls -lh /srv/backups
```

Jadwalkan harian 01:00 WIB (18:00 UTC) dengan `crontab -e` — sebelum offsite siap:

```
0 18 * * * cd /srv/umrovia && set -a && . /etc/umrovia/backup.env && set +a && infra/backup/backup.sh >> /srv/backups/backup.log 2>&1
```

Setelah offsite di bawah siap, ganti baris itu dengan versi yang juga menyalin ke bucket.

**Offsite ke NEO Object Storage** (produk *NSS Multi Region 2*: primer `https://nos.wjv-1.neo.id`,
replika `https://nos.jkt-1.neo.id`; bucket privat `umrovia-backups`). Simpan Access/Secret Key di
password manager dan tulis ke konfigurasi rclone tanpa menampilkannya:

```bash
read -rsp "Access Key: " AK; echo; read -rsp "Secret Key: " SK; echo
umask 077; mkdir -p ~/.config/rclone
cat > ~/.config/rclone/rclone.conf <<CONF
[neo]
type = s3
provider = Other
endpoint = https://nos.wjv-1.neo.id
access_key_id = $AK
secret_access_key = $SK
acl = private
bucket_acl = private
CONF
unset AK SK
rclone mkdir neo:umrovia-backups
rclone copy /srv/backups neo:umrovia-backups --include 'umrovia-*'
rclone check /srv/backups neo:umrovia-backups --include 'umrovia-*' --one-way   # 0 differences
curl -s -o /dev/null -w '%{http_code}\n' https://nos.wjv-1.neo.id/umrovia-backups/   # 403 = privat
```

Lalu jadwalkan `infra/backup/nightly.sh` (backup → salinan offsite → laporan Healthchecks)
sebagai pengganti baris cron di atas. Tambahkan ke `/etc/umrovia/backup.env`:

```
OFFSITE_REMOTE=neo:umrovia-backups
HC_PING_URL=https://hc-ping.com/<uuid-dari-healthchecks.io>
```

```
0 18 * * * /srv/umrovia/infra/backup/nightly.sh >> /srv/backups/backup.log 2>&1
```

**Healthchecks.io** (gratis): buat check `umrovia-backup`, jadwal Cron `0 18 * * *` zona UTC,
grace 1 jam, notifikasi email. Peringatan datang bila backup/salinan gagal (`/fail`) atau bila
tidak ada laporan sama sekali (cron/VPS mati).

Retensi 14 hari hanya berlaku di VPS; salinan di bucket tidak dihapus otomatis (ukuran kecil).
Pasang aturan lifecycle bucket bila ukurannya membesar.

**Drill restore bulanan** (BACKUP_RESTORE.md): unduh satu backup ke laptop dan jalankan
`infra/backup/restore_drill.sh` terhadap Postgres lokal — host VPS sengaja tidak
memasang klien Postgres.

## 8b. Midtrans produksi (top-up SaaS Wallet online)

Prasyarat: akun Midtrans sudah lolos aktivasi produksi (verifikasi bisnis).

1. Dashboard Midtrans → pindah lingkungan ke **Production** (sakelar di kiri atas).
2. **Settings → Access Keys**: salin **Server Key** (berawalan `Mid-server-`, bukan `SB-`).
3. **Settings → Configuration** (Payment): isi
   - Payment Notification URL: `https://api.umrovia.com/api/v1/payments/midtrans/notification`
   - Finish Redirect URL: `https://app.umrovia.com/dashboard/wallet`
4. Di VPS, isi key tanpa menampilkannya, lalu aktifkan mode produksi:

```bash
cd /srv/umrovia
read -rsp "Server Key Midtrans Production: " K; echo
K="$K" python3 -c 'import os,re;p=".env.production";s=open(p).read();s=re.sub(r"(?m)^MIDTRANS_SERVER_KEY=.*$",lambda m:"MIDTRANS_SERVER_KEY="+os.environ["K"],s);open(p,"w").write(s)'
unset K
sed -i 's/^MIDTRANS_IS_PRODUCTION=.*/MIDTRANS_IS_PRODUCTION=True/' .env.production
grep -q '^MIDTRANS_IS_PRODUCTION=' .env.production || echo 'MIDTRANS_IS_PRODUCTION=True' >> .env.production
docker compose up -d api worker
docker compose exec api python manage.py check | grep -E 'wallet\.W00' || echo "key & mode cocok"
```

`wallet.W001`/`W002` = key dan mode tertukar (sandbox vs produksi). Uji dengan top-up kecil dari
workspace travel berstatus ACTIVE (workspace TRIAL/demo tidak dapat top-up), pastikan saldo
bertambah setelah notifikasi Midtrans masuk, lalu `docker compose exec api python manage.py reconcile_wallets`.
Kembali ke sandbox: `MIDTRANS_IS_PRODUCTION=False` + key `SB-Mid-server-…`, lalu `docker compose up -d api worker`.

## 9. Monitoring

- NEO Sense (atau uptime checker lain), interval 1–5 menit:
  - `https://api.umrovia.com/api/v1/health/` → 200 dan `"database": "ok"`
  - `https://umrovia.com/` → 200
  - `https://app.umrovia.com/login` → 200
- Uji pemulihan otomatis sekali: `sudo reboot`, lalu pastikan `docker compose ps`
  kembali sehat tanpa campur tangan (Docker aktif saat boot, container `restart: unless-stopped`).
- Ambang & respons insiden: MONITORING_INCIDENT.md.

## 10. Deploy berikutnya & rollback

```bash
cd /srv/umrovia
(set -a; . /etc/umrovia/backup.env; set +a; infra/backup/backup.sh)   # backup pra-deploy
git pull --ff-only
docker compose up -d --build
SITE_HOST=umrovia.com APP_HOST=app.umrovia.com ADMIN_HOST=admin.umrovia.com API_HOST=api.umrovia.com \
  PORT=443 HTTP_PORT=80 infra/deploy/smoke.sh
```

Rollback kode: `git checkout <commit-sebelumnya> && docker compose up -d --build`
(aturan migrasi & restore: DEPLOY_ROLLBACK.md). Kembali ke cabang utama setelah selesai:
`git checkout main`.

## 11. Pemeliharaan rutin

| Kapan | Tindakan |
|---|---|
| Mingguan | `df -h /` (sisakan >20%), `cat /var/run/reboot-required 2>/dev/null` → reboot di jam sepi |
| Mingguan | `tail -n 20 /srv/backups/backup.log`, pastikan backup terbaru ada di object storage |
| Bulanan | Drill restore; `docker image prune -f` untuk image lama |
| Setelah HTTPS stabil | Naikkan `SECURE_HSTS_SECONDS` bertahap (DEPLOY_ROLLBACK.md), lalu `docker compose up -d` |

## 12. Masalah umum

| Gejala | Penyebab & solusi |
|---|---|
| `UNPROTECTED PRIVATE KEY FILE` | `chmod 600 ~/.ssh/umrovia.pem` |
| `Permission denied (publickey)` setelah bootstrap | User/kunci salah; masuk lewat konsol VNC Biznet Gio, cek `~bono2666/.ssh/authorized_keys` |
| Sertifikat tidak terbit (log proxy: ACME/challenge) | DNS belum mengarah ke IP VPS, atau port 80 tertutup di Security Group |
| Browser 502 | `api` belum sehat: `docker compose logs api` |
| `PII_ENCRYPTION_KEY wajib` / `ALLOWED_HOSTS` error | `.env.production` belum lengkap atau `COMPOSE_ENV_FILES` tidak ter-set |
| Error CORS di browser | `SITE_HOST`/`APP_HOST`/`API_HOST` tidak sama dengan domain yang dibuka; rebuild `web` setelah mengubah host |
| Build `web` terhenti (OOM) | Pastikan swap aktif (`swapon --show`), ulangi build |

## Masih terbuka sebelum go-live (GO_LIVE_CHECKLIST)

Dokumen jamaah masih di volume Docker (ikut backup harian) — pindahkan ke NEO Object
Storage privat butuh dukungan `django-storages`; pemindai antimalware unggahan;
Midtrans produksi; MFA role keuangan tenant; UAT manual oleh travel pilot.
