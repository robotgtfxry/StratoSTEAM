"""
UART link to ESP32 (bidirectional).
TX: sensor telemetry + image chunks.
RX: commands from ESP32 (photo request, cam_rec toggle).
"""
import json
import serial
from sensors import Bme280Data, Ms5611Data, Bno085Data, Ina219Data


class EspUartSender:
    def __init__(self, port: str, baud: int = 115200):
        self._ser = serial.Serial(port, baud, timeout=0)
        self._rx_buf = ""

    # ── TX ────────────────────────────────────────────────────────────────────

    def send(self, bme: Bme280Data, ms: Ms5611Data, imu: Bno085Data, pwr: Ina219Data) -> None:
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
        }
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        self._ser.write(line.encode())

    def send_img_chunk(self, img_id: int, seq: int, total: int, b64: str) -> None:
        """Send one image chunk to ESP32 for LoRa retransmission."""
        payload = {"type": "img", "id": img_id, "seq": seq, "tot": total, "data": b64}
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        self._ser.write(line.encode())

    # ── RX ────────────────────────────────────────────────────────────────────

    def read_cmd(self) -> dict | None:
        """Non-blocking read of one JSON command from ESP32. Returns dict or None."""
        while self._ser.in_waiting:
            c = self._ser.read(1).decode("utf-8", errors="ignore")
            if c == "\n":
                line = self._rx_buf.strip()
                self._rx_buf = ""
                if line:
                    try:
                        return json.loads(line)
                    except json.JSONDecodeError:
                        pass
            else:
                if len(self._rx_buf) < 512:
                    self._rx_buf += c
        return None

    def close(self) -> None:
        self._ser.close()
