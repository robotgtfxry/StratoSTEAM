#!/usr/bin/env python3
"""
StratoSTEAM — Air node
Reads all sensors, sends telemetry over LoRa every TELEMETRY_INTERVAL_S seconds,
then opens a short RX window to receive commands from the ground station.
"""
import logging
import time
import sys

from config import (
    GPS_PORT, GPS_BAUD,
    BME280_ADDR, MS5611_ADDR, BNO085_ADDR,
    INA219_ADDR, INA219_SHUNT_OHMS,
    TELEMETRY_INTERVAL_S, APRS_BEACON_INTERVAL_S,
    UPLINK_RX_WINDOW_S,
)
from sensors import (
    NeoM8nGps, Bme280Sensor, Ms5611Sensor, Bno085Sensor, Ina219Sensor,
)
from radio import LoRaSX1278, Ad9833Aprs
from hardware import Buzzer, RgbLed
from packet import build_packet, parse_command

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/var/log/stratosteam-air.log"),
    ],
)
log = logging.getLogger("air")


def apply_command(cmd: dict, buzzer: Buzzer, led: RgbLed):
    if "buzzer" in cmd:
        if cmd["buzzer"]:
            buzzer.on()
        else:
            buzzer.off()
        log.info("CMD buzzer → %s", cmd["buzzer"])

    if "led_r" in cmd or "led_g" in cmd or "led_b" in cmd:
        r = int(cmd.get("led_r", 0))
        g = int(cmd.get("led_g", 0))
        b = int(cmd.get("led_b", 0))
        led.set_color(r, g, b)
        log.info("CMD led → rgb(%d,%d,%d)", r, g, b)


def main():
    log.info("Initialising sensors…")
    gps    = NeoM8nGps(GPS_PORT, GPS_BAUD)
    bme    = Bme280Sensor(BME280_ADDR)
    ms     = Ms5611Sensor(MS5611_ADDR)
    imu    = Bno085Sensor()
    pwr    = Ina219Sensor(INA219_SHUNT_OHMS, INA219_ADDR)
    lora   = LoRaSX1278()
    aprs   = Ad9833Aprs()
    buzzer = Buzzer()
    led    = RgbLed()

    seq = 0
    last_telem = 0.0
    last_aprs  = 0.0

    log.info("Starting main loop")
    try:
        while True:
            gps.update()
            now = time.time()

            if now - last_telem >= TELEMETRY_INTERVAL_S:
                gps_d = gps.data
                bme_d = bme.read()
                ms_d  = ms.read()
                imu_d = imu.read()
                pwr_d = pwr.read()

                packet = build_packet(gps_d, bme_d, ms_d, imu_d, pwr_d, seq)
                ok = lora.send(packet)
                log.info(
                    "TX seq=%d ok=%s alt=%.0fm temp=%.1f°C batt=%.2fV",
                    seq, ok, gps_d.altitude_m or 0,
                    bme_d.temperature_c, pwr_d.voltage_v,
                )
                seq += 1
                last_telem = now

                # ── uplink window ─────────────────────────────────
                # ground station has UPLINK_RX_WINDOW_S to send a command
                raw_cmd = lora.listen(UPLINK_RX_WINDOW_S)
                if raw_cmd:
                    cmd = parse_command(raw_cmd)
                    if cmd:
                        apply_command(cmd, buzzer, led)

            if now - last_aprs >= APRS_BEACON_INTERVAL_S:
                gps_d = gps.data
                if gps_d.fix and gps_d.latitude and gps_d.longitude:
                    aprs.beacon(gps_d.latitude, gps_d.longitude, gps_d.altitude_m or 0)
                    log.info("APRS beacon sent")
                last_aprs = now

            time.sleep(0.05)

    except KeyboardInterrupt:
        log.info("Shutdown")
    finally:
        buzzer.close()
        led.close()
        gps.close()
        lora.close()
        aprs.close()


if __name__ == "__main__":
    main()
