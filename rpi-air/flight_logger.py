"""
Dziennik lotu na karcie RPi balonu — działa bez łączności z ziemią.

Co LOG_INTERVAL_S jeden wiersz ze wszystkim (czujniki, GPS z ESP32-S3, zasilanie, dysk,
kamera, faza lotu) do dwóch plików z godziną startu programu w nazwie:
    ~/stratosteam-logi/lot_20261126_101500.csv    — otwierasz w Excelu / LibreOffice
    ~/stratosteam-logi/lot_20261126_101500.jsonl  — jeden JSON na wiersz (pandas itp.)

Każdy wiersz trafia od razu do systemu, a co SYNC_S na kartę (fsync), więc nagłe odcięcie
zasilania zabiera najwyżej kilka ostatnich sekund. Błąd zapisu nigdy nie zatrzymuje lotu.
"""
import csv
import json
import logging
import os
import time
from datetime import datetime

log = logging.getLogger(__name__)

SYNC_S = 5

# Stała kolejność kolumn CSV (brakujące pola zostają puste)
FIELDS = [
    "czas", "ts", "od_startu_s", "lot",
    # GPS z ESP32-S3
    "gps_fix", "lat", "lon", "alt_gps", "pred_kmh", "kurs", "sat", "hdop",
    "sat_widoczne", "gps_snr", "gps_czas", "gps_wiek_s",
    # czujniki RPi
    "temp", "wilg", "cisn", "cisn2", "alt_baro",
    "roll", "pitch", "yaw", "ax", "ay", "az",
    # zasilanie i stan
    "v_bat", "prad_ma", "v_esp", "temp_cpu", "dysk_wolne_gb",
    "film", "plik_filmu", "lora", "esp_wiek_s",
    "espcam_ok", "espcam_rec", "espcam_klatki", "espcam_sd_mb",
]


class FlightLogger:
    def __init__(self, log_dir: str):
        self._dir = log_dir
        self._csv = self._jsonl = None
        self._writer = None
        self._t0 = time.monotonic()
        self._last_sync = 0.0
        self._last_warn = 0.0
        self.path = None
        self._open()

    def _open(self) -> None:
        try:
            os.makedirs(self._dir, exist_ok=True)
            base = os.path.join(self._dir, "lot_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
            n, name = 1, base
            while os.path.exists(name + ".csv"):    # zegar bez internetu może się cofnąć
                name = f"{base}_{n}"
                n += 1
            self._csv = open(name + ".csv", "w", newline="", encoding="utf-8")
            self._jsonl = open(name + ".jsonl", "a", encoding="utf-8")
            self._writer = csv.DictWriter(self._csv, fieldnames=FIELDS, extrasaction="ignore")
            self._writer.writeheader()
            self.path = name
            log.info("Dziennik lotu: %s.csv / .jsonl", name)
        except OSError as e:
            self._warn(e)
            self.close()

    def _warn(self, e: Exception) -> None:
        if time.monotonic() - self._last_warn > 60:
            log.error("Dziennik lotu: błąd zapisu (%s) — lot trwa dalej", e)
            self._last_warn = time.monotonic()

    def log(self, row: dict) -> None:
        if self._csv is None:
            if time.monotonic() - self._last_warn > 60:
                self._open()                        # np. karta była pełna — spróbuj ponownie
            if self._csv is None:
                return
        now = time.time()
        row = {"czas": datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S"),
               "ts": round(now, 1), "od_startu_s": round(time.monotonic() - self._t0, 1), **row}
        try:
            self._writer.writerow(row)
            self._jsonl.write(json.dumps({k: v for k, v in row.items() if v is not None},
                                         ensure_ascii=False) + "\n")
            self._csv.flush()
            self._jsonl.flush()
            if time.monotonic() - self._last_sync >= SYNC_S:
                os.fsync(self._csv.fileno())
                os.fsync(self._jsonl.fileno())
                self._last_sync = time.monotonic()
        except (OSError, ValueError) as e:
            self._warn(e)

    def close(self) -> None:
        for fh in (self._csv, self._jsonl):
            try:
                if fh:
                    fh.flush()
                    os.fsync(fh.fileno())
                    fh.close()
            except (OSError, ValueError):
                pass
        self._csv = self._jsonl = self._writer = None
