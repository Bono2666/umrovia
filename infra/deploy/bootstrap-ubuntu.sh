#!/usr/bin/env bash
# Bootstrap VPS Ubuntu 24.04 LTS untuk Umrovia (runbook FIRST_DEPLOY_VPS.md).
#
# Menjalankan sekaligus:
#   1. Akses SSH  — user deploy (sudo + SSH key), login password & root dimatikan
#   2. Firewall   — ufw: hanya SSH, 80, 443 yang terbuka
#   3. Update     — unattended-upgrades (patch keamanan) + fail2ban (sshd)
#   4. Docker     — Docker Engine + plugin Compose dari repositori resmi docker.com
#   5. Swap       — swapfile (bawaan 2G) + vm.swappiness=10
#   6. Waktu      — zona waktu UTC + sinkronisasi NTP
# Ditambah folder kerja /srv/umrovia, /srv/backups dan /etc/umrovia.
#
# Pemakaian (di VPS, sebagai user yang punya sudo):
#   sudo bash bootstrap-ubuntu.sh
#   sudo DEPLOY_USER=bono2666 SWAP_SIZE=2G SSH_PORT=22 bash bootstrap-ubuntu.sh
#
# Aman dijalankan ulang (idempoten). JANGAN tutup sesi SSH yang sedang terbuka
# sebelum login baru berhasil diuji dari terminal lain.
set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-${SUDO_USER:-}}"
SWAP_SIZE="${SWAP_SIZE:-2G}"
SSH_PORT="${SSH_PORT:-22}"
APP_DIR="${APP_DIR:-/srv/umrovia}"
BACKUP_DIR="${BACKUP_DIR:-/srv/backups}"
LOG=/var/log/umrovia-bootstrap.log

die() { echo "GAGAL: $*" >&2; exit 1; }
step() { printf '\n==> %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || die "jalankan dengan sudo: sudo bash $0"
if [ -z "$DEPLOY_USER" ] || [ "$DEPLOY_USER" = root ]; then
  die "set DEPLOY_USER=<user non-root>, mis. sudo DEPLOY_USER=bono2666 bash $0"
fi
[[ "$SSH_PORT" =~ ^[0-9]+$ ]] || die "SSH_PORT harus angka"
# shellcheck source=/dev/null
. /etc/os-release
[ "${ID:-}" = ubuntu ] || die "skrip ini untuk Ubuntu (terdeteksi: ${ID:-?})"
[ "${VERSION_ID:-}" = "24.04" ] || note "Peringatan: diuji untuk Ubuntu 24.04, terdeteksi ${VERSION_ID:-?}"

exec > >(tee -a "$LOG") 2>&1
echo "bootstrap Umrovia $(date -u +%FT%TZ) · user=$DEPLOY_USER · swap=$SWAP_SIZE · ssh=$SSH_PORT"
export DEBIAN_FRONTEND=noninteractive
APT=(apt-get -y -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)

step "0. Paket dasar & pembaruan sistem"
"${APT[@]}" update
"${APT[@]}" upgrade
"${APT[@]}" install ca-certificates curl gnupg git jq rclone ufw fail2ban python3-systemd unattended-upgrades

step "1. User deploy & hardening SSH"
if ! id "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
  note "user $DEPLOY_USER dibuat"
fi
usermod -aG sudo "$DEPLOY_USER"
HOME_DIR="$(getent passwd "$DEPLOY_USER" | cut -d: -f6)"
AUTH="$HOME_DIR/.ssh/authorized_keys"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$HOME_DIR/.ssh"
if [ ! -s "$AUTH" ]; then
  for src in /root/.ssh/authorized_keys /home/ubuntu/.ssh/authorized_keys; do
    if [ -s "$src" ]; then cp "$src" "$AUTH"; note "SSH key disalin dari $src"; break; fi
  done
fi
[ -s "$AUTH" ] || die "tidak ada SSH key di $AUTH. Tambahkan public key dulu; login password TIDAK dimatikan."
chown "$DEPLOY_USER:$DEPLOY_USER" "$AUTH"; chmod 600 "$AUTH"

# Login key-only: bila user tidak punya password, sudo tanpa password agar admin tidak terkunci.
if ! passwd -S "$DEPLOY_USER" | awk '{exit ($2 == "P") ? 0 : 1}'; then
  SUDOERS="/etc/sudoers.d/90-umrovia-$DEPLOY_USER"
  echo "$DEPLOY_USER ALL=(ALL) NOPASSWD:ALL" > "$SUDOERS"
  chmod 440 "$SUDOERS"
  visudo -cf "$SUDOERS" >/dev/null || { rm -f "$SUDOERS"; die "sudoers tidak valid"; }
  note "$DEPLOY_USER tidak punya password → sudo tanpa password (akses tetap dilindungi SSH key)"
fi

grep -qE '^\s*Include\s+/etc/ssh/sshd_config\.d/' /etc/ssh/sshd_config \
  || die "/etc/ssh/sshd_config tidak memuat Include sshd_config.d; hardening tidak bisa dipasang aman"
# Nama berawalan 00-: sshd memakai nilai PERTAMA yang ditemukan, jadi berkas ini harus dibaca
# sebelum 50-cloud-init.conf (yang sering menyalakan PasswordAuthentication).
cat > /etc/ssh/sshd_config.d/00-umrovia-hardening.conf <<EOF
# Dikelola infra/deploy/bootstrap-ubuntu.sh
Port $SSH_PORT
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
MaxAuthTries 4
X11Forwarding no
EOF
sshd -t || die "konfigurasi sshd tidak valid; tidak di-reload"
if systemctl is-active --quiet ssh.socket; then
  # Ubuntu 24.04: sshd diaktifkan lewat socket; port dibaca ulang dari konfigurasi saat daemon-reload.
  systemctl daemon-reload
  systemctl restart ssh.socket
fi
systemctl reload ssh 2>/dev/null || systemctl restart ssh
note "SSH: hanya key, root tidak boleh login, port $SSH_PORT"
[ "$SSH_PORT" = 22 ] || note "Port SSH diubah: buka port $SSH_PORT juga di Security Group Biznet Gio sebelum menutup sesi ini."

step "2. Firewall (ufw)"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow "$SSH_PORT/tcp" comment ssh >/dev/null
ufw allow 80/tcp comment http >/dev/null
ufw allow 443/tcp comment https >/dev/null
ufw --force enable >/dev/null
ufw status verbose | sed 's/^/    /'
note "Catatan: port yang dipublikasikan Docker melewati ufw. Stack Umrovia hanya memublikasikan 80/443 (Caddy);"
note "Postgres & Redis tetap di jaringan internal Docker — jangan tambahkan 'ports:' untuk keduanya."

step "3. Update keamanan otomatis & fail2ban"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
cat > /etc/apt/apt.conf.d/52umrovia-unattended <<'EOF'
// Patch keamanan otomatis; reboot dijadwalkan manual (cek /var/run/reboot-required).
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
EOF
systemctl enable --now unattended-upgrades >/dev/null
cat > /etc/fail2ban/jail.d/umrovia-sshd.local <<EOF
[sshd]
enabled  = true
port     = $SSH_PORT
backend  = systemd
maxretry = 5
findtime = 10m
bantime  = 1h
EOF
systemctl enable fail2ban >/dev/null
systemctl restart fail2ban
note "fail2ban aktif untuk sshd (5 percobaan gagal / 10 menit → blokir 1 jam)"

step "4. Docker Engine + Compose (repositori resmi docker.com)"
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
  if dpkg -s "$pkg" >/dev/null 2>&1; then "${APT[@]}" remove "$pkg"; fi
done
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list
"${APT[@]}" update
"${APT[@]}" install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
if [ ! -f /etc/docker/daemon.json ]; then
  # Batasi log container agar disk 60 GB tidak penuh oleh log.
  cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" }
}
EOF
  systemctl restart docker
fi
systemctl enable --now docker containerd >/dev/null
usermod -aG docker "$DEPLOY_USER"
note "$(docker --version) · $(docker compose version)"
note "$DEPLOY_USER masuk grup docker (setara root — lindungi SSH key-nya). Berlaku setelah login ulang."

step "5. Swap"
if swapon --show=NAME --noheadings | grep -q .; then
  note "swap sudah ada: $(swapon --show=NAME,SIZE --noheadings | tr '\n' ' ')"
else
  fallocate -l "$SWAP_SIZE" /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count="$(numfmt --from=iec "$SWAP_SIZE" | awk '{print int($1/1048576)}')" status=none
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  note "swapfile $SWAP_SIZE aktif"
fi
echo 'vm.swappiness=10' > /etc/sysctl.d/99-umrovia.conf
sysctl -q --system

step "6. Zona waktu & NTP"
timedatectl set-timezone UTC
timedatectl set-ntp true
note "UTC + NTP (aplikasi memakai zona waktu tiap travel, mis. Asia/Jakarta)"

step "Folder kerja"
install -d -m 755 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR"
install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$BACKUP_DIR" /etc/umrovia
note "$APP_DIR (kode), $BACKUP_DIR (backup terenkripsi), /etc/umrovia (secret backup, 700)"

step "Selesai"
cat <<EOF
    Langkah berikutnya (docs/runbooks/FIRST_DEPLOY_VPS.md, bagian 3):
    - Dari laptop, di terminal BARU, uji login: ssh -i <kunci> -p $SSH_PORT $DEPLOY_USER@<IP-VPS>
      Baru tutup sesi ini setelah login itu berhasil.
    - Login ulang agar grup docker aktif, lalu clone kode ke $APP_DIR.
    - Log bootstrap: $LOG
EOF
[ -f /var/run/reboot-required ] && note "Kernel/paket inti diperbarui: jadwalkan 'sudo reboot' setelah uji login berhasil."
exit 0
