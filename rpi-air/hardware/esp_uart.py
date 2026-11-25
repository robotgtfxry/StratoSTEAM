"""
Link to ESP32-S3 (bidirectional): USB cable if plugged in, otherwise UART wires.
TX: sensor telemetry + image chunks.
RX: commands from ESP32 (photo request, cam_rec toggle).
"""
import json
import logging
import termios
import time

import serial
from serial.tools import list_ports

from sensors import Bme280Data, Ms5611Data, Bno085Data, Ina219Data, Hx711Data


log = logging.getLogger(__name__)

S3_USB_IDS = {(0x1A86, 0x55D3)}     # CH343 na płytce ESP32-S3 (kamera ma inny: CH340)
CHECK_S = 5                         # co ile sprawdzać, czy kabel USB się pojawił / zniknął


def find_s3_usb() -> str | None:
    found = [p.device for p in list_ports.comports() if (p.vid, p.pid) in S3_USB_IDS]
    return found[0] if len(found) == 1 else None


class EspUartSender:
    def __init__(self, port: str, baud: int = 115200, use_usb: bool = True):
        self._uart_port = port
        self._baud = baud
        self._use_usb = use_usb
        self._ser: serial.Serial | None = None
        self._name = ""
        self._rx_buf = ""
        self._next_check = 0.0
        self._select()

    # ── Wybór łącza ───────────────────────────────────────────────────────────

    def _select(self) -> None:
        """Otwiera USB, a gdy go nie ma — UART. Błędy nie mogą zatrzymać lotu."""
        self._next_check = time.monotonic() + CHECK_S
        try:
            want = (find_s3_usb() if self._use_usb else None) or self._uart_port
            if self._ser is not None and want == self._name:
                return
            self._drop()
            ser = serial.Serial(want, self._baud, timeout=0, write_timeout=1)
            # DTR i RTS zostają oba włączone (domyślnie) — razem nie resetują S3.
            # Bez HUPCL zamknięcie portu też go nie zresetuje.
            attrs = termios.tcgetattr(ser.fileno())
            attrs[2] &= ~termios.HUPCL
            termios.tcsetattr(ser.fileno(), termios.TCSANOW, attrs)
            self._ser, self._name, self._rx_buf = ser, want, ""
            log.info("ESP32: łącze %s", want)
        except (OSError, termios.error) as e:       # SerialException dziedziczy po OSError
            log.warning("ESP32: nie mogę otworzyć łącza (%s)", e)
            self._drop()

    def _drop(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            except OSError:
                pass
        self._ser, self._name = None, ""

    def _write(self, payload: dict) -> None:
        if time.monotonic() >= self._next_check:
            self._select()
        if self._ser is None:
            return
        try:
            self._ser.write((json.dumps(payload, separators=(",", ":")) + "\n").encode())
        except OSError as e:
            log.warning("ESP32: błąd zapisu (%s)", e)
            self._drop()

    # ── TX ────────────────────────────────────────────────────────────────────

    def send(self, bme: Bme280Data, ms: Ms5611Data, imu: Bno085Data, pwr: Ina219Data,
             disk_used_gb: float = 0.0, disk_free_gb: float = 0.0,
             hf_dbfs: float | None = None,
             strains: list[Hx711Data] | None = None,
             espcam_status: list | None = None) -> None:
        payload = {
            "temp": bme.temperature_c,
            "hum":  bme.humidity_pct,
            "pres": bme.pressure_hpa,
            "p2":   ms.pressure_hpa,
            "alt2": ms.altitude_m,
            "roll": imu.roll_deg,
            "pit":  imu.pitch_deg,
            "yaw":  imu.yaw_deg,
            "ax":   imu.accel_x,
            "ay":   imu.accel_y,
            "az":   imu.accel_z,
            "vbat": pwr.voltage_v,
            "imA":  pwr.current_ma,
            "dsku": disk_used_gb,
            "dskf": disk_free_gb,
        }
        if hf_dbfs is not None:
            payload["hfdb"] = hf_dbfs
        if strains:
            for i, s in enumerate(strains):
                payload[f"sg{i}"] = s.strain_g
        # espcam_status: [ok, rec, frames, free_mb] — jedna kamera ESP32-CAM
        if espcam_status:
            payload["ec"] = espcam_status
        self._write(payload)

    def send_img_chunk(self, img_id: int, seq: int, total: int, b64: str) -> None:
        """Send one image chunk to ESP32 for LoRa retransmission."""
        self._write({"type": "img", "id": img_id, "seq": seq, "tot": total, "data": b64})

    # ── RX ────────────────────────────────────────────────────────────────────

    def read_cmd(self) -> dict | None:
        """Non-blocking read of one JSON command from ESP32. Returns dict or None."""
        if self._ser is None:
            return None
        try:
            while self._ser.in_waiting:
                c = self._ser.read(1).decode("utf-8", errors="ignore")
                if c != "\n":
                    if len(self._rx_buf) < 512:
                        self._rx_buf += c
                    continue
                line, self._rx_buf = self._rx_buf.strip(), ""
                if not line.startswith("{"):        # przez USB lecą też logi S3
                    continue
                try:
                    cmd = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(cmd, dict):
                    return cmd
        except OSError as e:
            log.warning("ESP32: błąd odczytu (%s)", e)
            self._drop()
        return None

    def close(self) -> None:
        self._drop()
