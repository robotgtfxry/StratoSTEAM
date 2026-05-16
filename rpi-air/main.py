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
    ESP_UART_PORT, ESP_UART_BAUD, ESP_SEND_INTERVAL_S,
    CAM_RECORD_DIR, CAM_PHOTO_W, CAM_PHOTO_H, CAM_PHOTO_QUALITY, CAM_CHUNK_INTERVAL_S,
    SDR_ENABLED, SDR_TARGET_FREQ, SDR_SAMPLE_RATE, SDR_GAIN,
    SDR_FREQ_CORRECTION, SDR_MEASURE_INTERVAL_S, SDR_NUM_SAMPLES, SDR_BIN_WINDOW,
)
from sensors import Bme280Sensor, Ms5611Sensor, Bno085Sensor, Ina219Sensor
from hardware import PowerSignal, EspUartSender, CameraModule, SdrReceiver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/var/log/stratosteam-air.log"),
    ],
)
log = logging.getLogger("air")


def main():
    log.info("Initialising sensors…")
    power = PowerSignal()
    power.set_alive(True)

    bme  = Bme280Sensor(BME280_ADDR)
    ms   = Ms5611Sensor(MS5611_ADDR)
    imu  = Bno085Sensor()
    pwr  = Ina219Sensor(INA219_SHUNT_OHMS, INA219_ADDR)
    esp  = EspUartSender(ESP_UART_PORT, ESP_UART_BAUD)
    cam  = CameraModule(CAM_RECORD_DIR, CAM_PHOTO_W, CAM_PHOTO_H, CAM_PHOTO_QUALITY)
    sdr  = SdrReceiver(
        target_freq_hz  = SDR_TARGET_FREQ,
        sample_rate     = SDR_SAMPLE_RATE,
        gain            = SDR_GAIN,
        freq_correction = SDR_FREQ_CORRECTION,
        num_samples     = SDR_NUM_SAMPLES,
        bin_window      = SDR_BIN_WINDOW,
    ) if SDR_ENABLED else None

    # Start recording immediately on boot if camera is available
    if cam.available:
        cam.start_recording()

    last_send       = 0.0
    pending_chunks: list[tuple[int, int, int, str]] = []
    last_chunk_sent = 0.0
    last_sdr        = 0.0
    last_hf_dbfs: float | None = None

    log.info("Starting main loop")
    try:
        while True:
            now = time.time()

            # ── Sprawdź czy ESP32 prosi o shutdown ───────────────────────────
            if power.shutdown_requested:
                log.info("Shutdown requested by ESP32 — shutting down OS")
                power.set_alive(False)
                os.system("sudo shutdown -h now")
                break

            # ── Komendy z ESP32 (photo / cam_rec) ────────────────────────────
            cmd = esp.read_cmd()
            if cmd:
                c = cmd.get("cmd", "")
                if c == "photo" and cam.available:
                    chunks = cam.capture_photo_chunks()
                    if chunks:
                        pending_chunks.extend(chunks)
                        log.info("Photo queued: %d chunks pending", len(pending_chunks))
                    else:
                        log.warning("Photo capture returned no chunks")

                elif c == "cam_rec" and cam.available:
                    if cmd.get("on", False):
                        cam.start_recording()
                    else:
                        cam.stop_recording()

            # ── Wysyłaj chunki obrazu do ESP32 (po jednym co CAM_CHUNK_INTERVAL_S) ──
            if pending_chunks and (now - last_chunk_sent >= CAM_CHUNK_INTERVAL_S):
                img_id, seq, total, b64 = pending_chunks.pop(0)
                esp.send_img_chunk(img_id, seq, total, b64)
                last_chunk_sent = now
                log.info("→ESP32 img chunk %d/%d (id=%d)", seq + 1, total, img_id)

            # ── Pomiar SDR (nie blokuje — sprawdź timer) ─────────────────────
            if sdr and sdr.available and (now - last_sdr >= SDR_MEASURE_INTERVAL_S):
                dbfs = sdr.measure()
                if dbfs != -999.0:
                    last_hf_dbfs = dbfs
                    log.info("SDR: %.1f dBFS @ %.3f MHz", dbfs, SDR_TARGET_FREQ / 1e6)
                last_sdr = now

            # ── Wyślij dane czujników do ESP32 przez UART ─────────────────────
            if now - last_send >= ESP_SEND_INTERVAL_S:
                bme_d = bme.read()
                ms_d  = ms.read()
                imu_d = imu.read()
                pwr_d = pwr.read()

                disk_used, disk_free = cam.disk_usage(CAM_RECORD_DIR)
                esp.send(bme_d, ms_d, imu_d, pwr_d,
                         disk_used_gb=disk_used, disk_free_gb=disk_free,
                         hf_dbfs=last_hf_dbfs)
                log.info(
                    "→ESP32 temp=%.1f°C pres=%.1fhPa alt2=%.0fm vbat=%.2fV disk=%.1f/%.1fGB",
                    bme_d.temperature_c, bme_d.pressure_hpa,
                    ms_d.altitude_m, pwr_d.voltage_v, disk_used, disk_free,
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
        power.close()


if __name__ == "__main__":
    main()
