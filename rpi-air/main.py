#!/usr/bin/env python3
"""
StratoSTEAM — Air node
Reads all sensors, forwards data to ESP32 over UART (ESP32 handles LoRa TX).
Signals ESP32-S3 that RPi is alive; handles graceful shutdown on ESP32 request.
"""
import logging
import time
import sys
import os

from config import (
    BME280_ADDR, MS5611_ADDR, BNO085_ADDR,
    INA219_ADDR, INA219_SHUNT_OHMS,
    SENSOR_SET, MPU6050_ADDR, BMP180_ADDR, INA226_ADDR, INA226_SHUNT_OHMS,
    ESPCAM_PWR_PIN, ESPCAM_UART_PORT, ESPCAM_STATUS_BAUD,
    ESP_UART_PORT, ESP_UART_BAUD, ESP_USB_ENABLED, ESP_SEND_INTERVAL_S,
    CAM_RECORD_DIR, CAM_PHOTO_BY_SF, FLIGHT_FLAG, PREVIEW_PORT,
    CAM_RECORD_W, CAM_RECORD_H, CAM_RECORD_FPS, CAM_RECORD_BITRATE,
    SDR_ENABLED, SDR_TARGET_FREQ, SDR_SAMPLE_RATE, SDR_GAIN,
    SDR_FREQ_CORRECTION, SDR_MEASURE_INTERVAL_S, SDR_NUM_SAMPLES, SDR_BIN_WINDOW,
)
from sensors import (
    Bme280Sensor, Ms5611Sensor, Bno085Sensor, Ina219Sensor,
    Mpu6050Sensor, Bmp180Sensor, Ina226Sensor,
    Bme280Data, Ms5611Data, Bno085Data, Ina219Data,
)
from hardware import PowerSignal, EspUartSender, CameraModule, SdrReceiver, EspCamPower, EspCamMonitor, \
    start_preview_server


def _log_handlers() -> list[logging.Handler]:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    for path in ("/var/log/stratosteam-air.log",
                 os.path.join(os.path.dirname(os.path.abspath(__file__)), "stratosteam-air.log")):
        try:
            handlers.append(logging.FileHandler(path))
            break
        except OSError:
            continue
    return handlers


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=_log_handlers(),
)
log = logging.getLogger("air")


class _MissingSensor:
    """Zastępuje czujnik, którego nie udało się zainicjalizować — zwraca wartości domyślne."""

    def __init__(self, data_cls):
        self._data_cls = data_cls

    def read(self):
        return self._data_cls()


class _NullEsp:
    """Zastępuje UART do ESP32, gdy port nie jest dostępny."""

    def send(self, *args, **kwargs) -> None:
        pass

    def send_photo(self, *args, **kwargs) -> None:
        pass

    def read_cmd(self) -> None:
        return None

    def close(self) -> None:
        pass


def _init(name: str, factory, fallback):
    try:
        obj = factory()
        log.info("%s: OK", name)
        return obj
    except Exception as exc:
        log.error("%s: init failed (%s) — continuing without it", name, exc)
        return fallback


def main():
    log.info("Initialising sensors…")
    power = PowerSignal()
    power.set_alive(True)

    bme    = _init("BME280", lambda: Bme280Sensor(BME280_ADDR), _MissingSensor(Bme280Data))
    if SENSOR_SET == "gy87":
        ms  = _init("BMP180", lambda: Bmp180Sensor(BMP180_ADDR), _MissingSensor(Ms5611Data))
        imu = _init("MPU-6050", lambda: Mpu6050Sensor(MPU6050_ADDR), _MissingSensor(Bno085Data))
        pwr = _init("INA226", lambda: Ina226Sensor(INA226_SHUNT_OHMS, INA226_ADDR),
                    _MissingSensor(Ina219Data))
    else:
        ms  = _init("MS5611", lambda: Ms5611Sensor(MS5611_ADDR), _MissingSensor(Ms5611Data))
        imu = _init("BNO085", Bno085Sensor, _MissingSensor(Bno085Data))
        pwr = _init("INA219", lambda: Ina219Sensor(INA219_SHUNT_OHMS, INA219_ADDR),
                    _MissingSensor(Ina219Data))
    espcam     = EspCamPower(ESPCAM_PWR_PIN)
    espcam_mon = EspCamMonitor(ESPCAM_UART_PORT, ESPCAM_STATUS_BAUD)
    esp        = _init("ESP32 UART", lambda: EspUartSender(ESP_UART_PORT, ESP_UART_BAUD, ESP_USB_ENABLED),
                       _NullEsp())
    cam  = CameraModule(CAM_RECORD_DIR, CAM_RECORD_W, CAM_RECORD_H, CAM_RECORD_FPS, CAM_RECORD_BITRATE)
    sdr  = SdrReceiver(
        target_freq_hz  = SDR_TARGET_FREQ,
        sample_rate     = SDR_SAMPLE_RATE,
        gain            = SDR_GAIN,
        freq_correction = SDR_FREQ_CORRECTION,
        num_samples     = SDR_NUM_SAMPLES,
        bin_window      = SDR_BIN_WINDOW,
    ) if SDR_ENABLED else None

    if cam.available and PREVIEW_PORT:
        start_preview_server(cam, PREVIEW_PORT)

    # Start recording immediately on boot if camera is available
    if cam.available:
        cam.start_recording()

    last_send       = 0.0
    photo_id    = int(time.time()) % 250      # po restarcie inny numer niż poprzednio
    photo_data: bytes | None = None           # zdjęcie czekające na potwierdzenie S3
    photo_tries = 0
    photo_sent  = 0.0
    cam.set_flight(os.path.exists(FLIGHT_FLAG))
    esp_lora_ok = None          # ostatni stan LoRa zgłoszony przez ESP32
    esp_last_status = time.time()
    esp_link_warned = False
    last_sdr        = 0.0
    last_hf_dbfs: float | None = None

    log.info("Starting main loop")
    try:
        while True:
            now = time.time()

            # ── Sprawdź czy ESP32 prosi o shutdown ───────────────────────────
            if power.shutdown_requested:
                # ALIVE zostaje HIGH do zamknięcia usługi — ESP32 odcina prąd dopiero
                # RPI_HALT_DELAY_MS po jego opadnięciu.
                log.info("Shutdown requested by ESP32 — shutting down OS")
                if os.system("sudo -n /usr/sbin/shutdown -h now") != 0:
                    log.error("shutdown nieudany — brak uprawnień? uruchom: sudo bash setup.sh")
                break

            # ── Komendy z ESP32 (photo / cam_rec) ────────────────────────────
            cmd = esp.read_cmd()
            if cmd:
                c = cmd.get("cmd", "")
                if cmd.get("type") == "esp_status":
                    lora = bool(cmd.get("lora", False))
                    if lora != esp_lora_ok:
                        if lora:
                            log.info("ESP32: LoRa OK (ESP odebrało %s linii z RPi)", cmd.get("rx"))
                        else:
                            log.warning("ESP32: BRAK LoRa — telemetria NIE jest nadawana radiowo "
                                        "(UART działa, ESP odebrało %s linii z RPi)", cmd.get("rx"))
                        esp_lora_ok = lora
                    esp_last_status = now

                elif cmd.get("type") == "imgst":
                    if photo_data is not None and cmd.get("id") == photo_id:
                        if cmd.get("ok"):
                            log.info("ESP32: zdjęcie id=%d przyjęte", photo_id)
                            photo_data = None
                        else:
                            photo_sent = 0.0        # ponów od razu

                elif c == "photo" and cam.available:
                    sf = min(max(int(cmd.get("sf", 10)), 7), 10)
                    photo_data = cam.capture_photo(*CAM_PHOTO_BY_SF[sf])
                    photo_id = photo_id % 250 + 1
                    photo_tries, photo_sent = 0, 0.0

                elif c == "flight":
                    on = bool(cmd.get("on", False))
                    try:
                        if on:
                            open(FLIGHT_FLAG, "w").close()
                        elif os.path.exists(FLIGHT_FLAG):
                            os.remove(FLIGHT_FLAG)
                    except OSError as exc:
                        log.warning("flaga lotu: %s", exc)
                    cam.set_flight(on)

                elif c == "cam_rec" and cam.available:
                    if cmd.get("on", False):
                        cam.start_recording()
                    else:
                        cam.stop_recording()

                elif c == "espcam_pwr":
                    espcam.set(bool(cmd.get("on", False)))

            # ── Brak statusu z ESP32 (co 5 s) → link UART ESP→RPi nie działa ──
            if now - esp_last_status > 15 and not esp_link_warned:
                log.warning("ESP32: brak statusu przez UART od 15 s — sprawdź ESP (zasilanie/GND/GPIO14→GPIO15)")
                esp_link_warned = True
            elif now - esp_last_status <= 15 and esp_link_warned:
                log.info("ESP32: link UART przywrócony")
                esp_link_warned = False

            # ── Zdjęcie do S3 — ponawiaj, aż potwierdzi (max 3 razy) ──────────
            if photo_data is not None and now - photo_sent > 8:
                if photo_tries >= 3:
                    log.error("ESP32 nie przyjął zdjęcia id=%d", photo_id)
                    photo_data = None
                else:
                    photo_tries += 1
                    esp.send_photo(photo_id, photo_data)
                    photo_sent = time.time()
                    log.info("→ESP32 zdjęcie id=%d %d B (próba %d)", photo_id, len(photo_data), photo_tries)

            # ── Pomiar SDR (nie blokuje — sprawdź timer) ─────────────────────
            if sdr and sdr.available and (now - last_sdr >= SDR_MEASURE_INTERVAL_S):
                dbfs = sdr.measure()
                if dbfs != -999.0:
                    last_hf_dbfs = dbfs
                    log.info("SDR: %.1f dBFS @ %.3f MHz", dbfs, SDR_TARGET_FREQ / 1e6)
                last_sdr = now

            # ── Wyślij dane czujników do ESP32 przez UART ─────────────────────
            if now - last_send >= ESP_SEND_INTERVAL_S:
                bme_d    = bme.read()
                ms_d     = ms.read()
                imu_d    = imu.read()
                pwr_d    = pwr.read()

                disk_used, disk_free = cam.disk_usage(CAM_RECORD_DIR)
                esp.send(bme_d, ms_d, imu_d, pwr_d,
                         disk_used_gb=disk_used, disk_free_gb=disk_free,
                         hf_dbfs=last_hf_dbfs,
                         espcam_status=espcam_mon.compact())
                log.info(
                    "→ESP32 temp=%.1f°C alt2=%.0fm vbat=%.2fV",
                    bme_d.temperature_c, ms_d.altitude_m, pwr_d.voltage_v,
                )
                last_send = now

            time.sleep(0.05)

    except KeyboardInterrupt:
        log.info("Shutdown by keyboard")
    finally:
        power.set_alive(False)
        cam.close()
        if sdr:
            sdr.close()
        esp.close()
        espcam_mon.stop()
        espcam.close()
        power.close()


if __name__ == "__main__":
    main()
