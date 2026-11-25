#!/bin/bash
# StratoSTEAM rpi-air — jednorazowa konfiguracja systemu (uruchom: sudo bash setup.sh)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="${SUDO_USER:-admin}"
CFG=/boot/firmware/config.txt

# I2C (bus 1, GPIO2/3), UART0 na GPIO14/15 → /dev/ttyAMA0
grep -q '^dtparam=i2c_arm=on' "$CFG" || echo 'dtparam=i2c_arm=on' >> "$CFG"
grep -q '^dtparam=uart0=on'   "$CFG" || echo 'dtparam=uart0=on'   >> "$CFG"
# ESP32-CAM jest teraz na USB — UART3 (GPIO8/9) już niepotrzebny
sed -i '/^dtoverlay=uart3-pi5[[:space:]]*$/d' "$CFG"
grep -q '^i2c-dev' /etc/modules || echo 'i2c-dev' >> /etc/modules

# Biblioteka RTL-SDR (dla pyrtlsdr)
apt-get install -y librtlsdr2 || apt-get install -y librtlsdr0 || true

# adafruit-blinka dociąga RPi.GPIO — na RPi 5 nie działa i przesłania systemowe rpi-lgpio
if [ -x "$DIR/.venv/bin/pip" ]; then
    sudo -u "$USER_NAME" "$DIR/.venv/bin/pip" uninstall -y RPi.GPIO || true
fi

# ESP32-CAM na USB (CH340): prawo do portu; ModemManager ma go nie ruszać
usermod -aG dialout "$USER_NAME"
echo 'SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", ENV{ID_MM_DEVICE_IGNORE}="1"' \
    > /etc/udev/rules.d/99-stratosteam-espcam.rules
udevadm control --reload-rules || true
# brltty (czytnik brajla) przejmuje CH340 i port ttyUSB znika
if dpkg -s brltty >/dev/null 2>&1; then
    systemctl mask --now brltty.service brltty-udev.service || true
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
