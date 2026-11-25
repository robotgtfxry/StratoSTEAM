#!/bin/bash
# StratoSTEAM rpi-air — jednorazowa konfiguracja systemu (uruchom: sudo bash setup.sh)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${SUDO_USER:-admin}"
CFG=/boot/firmware/config.txt

# I2C (bus 1, GPIO2/3), UART0 na GPIO14/15 → /dev/ttyAMA0,
# UART3 na GPIO8/9 (status ESP32-CAM) → /dev/ttyAMA3
grep -q '^dtparam=i2c_arm=on' "$CFG" || echo 'dtparam=i2c_arm=on' >> "$CFG"
grep -q '^dtparam=uart0=on'   "$CFG" || echo 'dtparam=uart0=on'   >> "$CFG"
grep -q '^dtoverlay=uart3-pi5' "$CFG" || printf '\n[all]\ndtoverlay=uart3-pi5\n' >> "$CFG"
grep -q '^i2c-dev' /etc/modules || echo 'i2c-dev' >> /etc/modules

# Biblioteka RTL-SDR (dla pyrtlsdr)
apt-get install -y librtlsdr2 || apt-get install -y librtlsdr0 || true

# adafruit-blinka dociąga RPi.GPIO — na RPi 5 nie działa i przesłania systemowe rpi-lgpio
if [ -x "$DIR/.venv/bin/pip" ]; then
    sudo -u "$USER_NAME" "$DIR/.venv/bin/pip" uninstall -y RPi.GPIO || true
fi

# Plik logu
touch /var/log/stratosteam-air.log
chown "$USER_NAME" /var/log/stratosteam-air.log

# Usługa może zamknąć system bez hasła (prośba ESP32 o shutdown)
SUDOERS=/etc/sudoers.d/stratosteam
TMP="$(mktemp)"
echo "$USER_NAME ALL=(root) NOPASSWD: /usr/sbin/shutdown -h now" > "$TMP"
visudo -cf "$TMP"
install -m 0440 -o root -g root "$TMP" "$SUDOERS"
rm -f "$TMP"

# Usługa systemd
cp "$DIR/rpi-air.service" /etc/systemd/system/rpi-air.service
systemctl daemon-reload
systemctl enable rpi-air.service

echo "Gotowe. Zrób reboot (sudo reboot) — po starcie usługa rpi-air uruchomi się sama."
