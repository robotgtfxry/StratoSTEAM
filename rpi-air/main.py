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
    APRS_BEACON_INTERVAL_S, APRS_BEACON_DURATION_S,
)
from sensors import Bme280Sensor, Ms5611Sensor, Bno085Sensor, Ina219Sensor
from radio import Ad9833Aprs
from hardware import PowerSignal, EspUartSender

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
    aprs = Ad9833Aprs()

    last_send = 0.0
    last_aprs = 0.0
    aprs_on   = False
    aprs_on_at = 0.0

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

            # ── Wyślij dane czujników do ESP32 przez UART ─────────────────────
            if now - last_send >= ESP_SEND_INTERVAL_S:
                bme_d = bme.read()
                ms_d  = ms.read()
                imu_d = imu.read()
                pwr_d = pwr.read()

                esp.send(bme_d, ms_d, imu_d, pwr_d)
                log.info(
                    "→ESP32 temp=%.1f°C pres=%.1fhPa alt2=%.0fm vbat=%.2fV",
                    bme_d.temperature_c, bme_d.pressure_hpa,
                    ms_d.altitude_m, pwr_d.voltage_v,
                )
                last_send = now

            # ── APRS: włącz nośną na APRS_BEACON_DURATION_S sekund ───────────
            if not aprs_on and (now - last_aprs >= APRS_BEACON_INTERVAL_S):
                aprs.start()
                aprs_on    = True
                aprs_on_at = now
                log.info("APRS carrier ON (%.0f MHz)", 144.8)

            if aprs_on and (now - aprs_on_at >= APRS_BEACON_DURATION_S):
                aprs.stop()
                aprs_on   = False
                last_aprs = now
                log.info("APRS carrier OFF")

            time.sleep(0.05)

    except KeyboardInterrupt:
        log.info("Shutdown by keyboard")
    finally:
        power.set_alive(False)
        esp.close()
        aprs.close()
        power.close()


if __name__ == "__main__":
    main()
