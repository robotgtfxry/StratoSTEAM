"""Sends sensor telemetry to ESP32 over UART (one-way TX, line-delimited JSON)."""
import json
import serial
from sensors import Bme280Data, Ms5611Data, Bno085Data, Ina219Data


class EspUartSender:
    def __init__(self, port: str, baud: int = 115200):
        self._ser = serial.Serial(port, baud, timeout=0)

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

    def close(self) -> None:
        self._ser.close()
