"""
FlightLogger — zapisuje wszystkie odczyty czujników do pliku CSV i JSONL
od momentu uruchomienia systemu.

Pliki są tworzone w LOG_DIR z datą/godziną startu misji w nazwie:
    /var/log/stratosteam/flight_20260504_143000.csv
    /var/log/stratosteam/flight_20260504_143000.jsonl

Format JSONL: jeden JSON-object na linię (łatwy import do pandas/Excel).
Format CSV:   nagłówek + wiersze, otwierany w Libre/Excel.
"""
import csv
import json
import logging
import os
import time
from dataclasses import asdict
from datetime import datetime, timezone

from sensors import GpsData, Bme280Data, Ms5611Data, Bno085Data, Ina219Data

LOG_DIR = "/var/log/stratosteam"
log = logging.getLogger(__name__)


class FlightLogger:
    def __init__(self, log_dir: str = LOG_DIR):
        os.makedirs(log_dir, exist_ok=True)
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path   = os.path.join(log_dir, f"flight_{ts_str}.csv")
        jsonl_path = os.path.join(log_dir, f"flight_{ts_str}.jsonl")

        self._csv_fh   = open(csv_path,   "w", newline="", encoding="utf-8")
        self._jsonl_fh = open(jsonl_path, "a", encoding="utf-8")
        self._writer: csv.DictWriter | None = None
        self._start_time = time.time()

        log.info("FlightLogger started: %s / %s", csv_path, jsonl_path)

    # ── public API ────────────────────────────────────────────────────────────

    def log(
        self,
        seq: int,
        gps: GpsData,
        bme: Bme280Data,
        ms:  Ms5611Data,
        imu: Bno085Data,
        pwr: Ina219Data,
    ) -> None:
        row = self._build_row(seq, gps, bme, ms, imu, pwr)

        # JSONL — zawsze flush
        self._jsonl_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._jsonl_fh.flush()

        # CSV — nagłówek tylko raz (pierwsza linia)
        if self._writer is None:
            self._writer = csv.DictWriter(
                self._csv_fh, fieldnames=list(row.keys())
            )
            self._writer.writeheader()
        self._writer.writerow(row)
        self._csv_fh.flush()

    def close(self) -> None:
        try:
            self._csv_fh.close()
            self._jsonl_fh.close()
            log.info("FlightLogger closed")
        except Exception as e:
            log.warning("FlightLogger close error: %s", e)

    # ── private ───────────────────────────────────────────────────────────────

    def _build_row(
        self,
        seq: int,
        gps: GpsData,
        bme: Bme280Data,
        ms:  Ms5611Data,
        imu: Bno085Data,
        pwr: Ina219Data,
    ) -> dict:
        now = time.time()
        return {
            # czas
            "seq":           seq,
            "unix_ts":       int(now),
            "elapsed_s":     round(now - self._start_time, 1),
            "utc_datetime":  datetime.now(timezone.utc).isoformat(timespec="seconds"),

            # GPS
            "lat":           gps.latitude,
            "lon":           gps.longitude,
            "alt_gps_m":     gps.altitude_m,
            "speed_kmh":     gps.speed_kmh,
            "heading_deg":   gps.heading,
            "satellites":    gps.satellites,
            "gps_fix":       gps.fix,

            # BME280 — temperatura, wilgotność, ciśnienie
            "bme_temp_c":    bme.temperature_c,
            "bme_hum_pct":   bme.humidity_pct,
            "bme_pres_hpa":  bme.pressure_hpa,

            # MS5611 — barometr precyzyjny
            "ms_temp_c":     ms.temperature_c,
            "ms_pres_hpa":   ms.pressure_hpa,
            "ms_alt_m":      ms.altitude_m,

            # BNO085 — IMU
            "roll_deg":      imu.roll_deg,
            "pitch_deg":     imu.pitch_deg,
            "yaw_deg":       imu.yaw_deg,
            "accel_x_g":     imu.accel_x,
            "accel_y_g":     imu.accel_y,
            "accel_z_g":     imu.accel_z,

            # INA219 — zasilanie
            "voltage_v":     pwr.voltage_v,
            "current_ma":    pwr.current_ma,
            "power_mw":      pwr.power_mw,
        }
