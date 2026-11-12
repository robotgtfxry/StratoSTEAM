#!/bin/bash
# StratoSTEAM rpi-air — jednorazowa konfiguracja systemu (uruchom: sudo bash setup.sh)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${SUDO_USER:-admin}"
CFG=/boot/firmware/config.txt

# I2C (bus 1, GPIO2/3) i UART0 na GPIO14/15 → /dev/ttyAMA0
grep -q '^dtparam=i2c_arm=on' "$CFG" || echo 'dtparam=i2c_arm=on' >> "$CFG"
grep -q '^dtparam=uart0=on'   "$CFG" || echo 'dtparam=uart0=on'   >> "$CFG"
grep -q '^i2c-dev' /etc/modules || echo 'i2c-dev' >> /etc/modules

# Biblioteka RTL-SDR (dla pyrtlsdr)
apt-get install -y librtlsdr2 || apt-get install -y librtlsdr0 || true

# Plik logu
touch /var/log/stratosteam-air.log
chown "$USER_NAME" /var/log/stratosteam-air.log

# Usługa systemd
cp "$DIR/rpi-air.service" /etc/systemd/system/rpi-air.service
systemctl daemon-reload
systemctl enable rpi-air.service

echo "Gotowe. Zrób reboot (sudo reboot) — po starcie usługa rpi-air uruchomi się sama."
