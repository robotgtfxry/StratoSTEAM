#!/usr/bin/env python3
"""
StratoSTEAM — Air node
Reads all sensors, sends telemetry over LoRa, opens uplink window for commands.
Signals ESP32-S3 that RPi is alive; handles graceful shutdown on ESP32 request.
"""
import logging
import time
import sys
import os
import subprocess

from config import (
    GPS_PORT, GPS_BAUD,
    BME280_ADDR, MS5611_ADDR, BNO085_ADDR,
    INA219_ADDR, INA219_SHUNT_OHMS,
    TELEMETRY_INTERVAL_S, APRS_BEACON_INTERVAL_S, APRS_BEACON_DURATION_S,
    UPLINK_RX_WINDOW_S,
)
from sensors import (
    NeoM8nGps, Bme280Sensor, Ms5611Sensor, Bno085Sensor, Ina219Sensor,
)
from radio import LoRaSX1278, Ad9833Aprs
from hardware import Buzzer, RgbLed, PowerSignal
from packet import build_packet, parse_command, build_exec_result

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
    power  = PowerSignal()
    power.set_alive(True)   # informuj ESP32 że RPi działa

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
    last_telem  = 0.0
    last_aprs   = 0.0
    aprs_on     = False
    aprs_on_at  = 0.0
    exec_result: bytes | None = None   # wynik do odesłania w następnym TX

    log.info("Starting main loop")
    try:
        while True:
            gps.update()
            now = time.time()

            # ── Sprawdź czy ESP32 prosi o shutdown ───────────────────────────
            if power.shutdown_requested:
                log.info("Shutdown requested by ESP32 — shutting down OS")
                power.set_alive(False)
                os.system("sudo shutdown -h now")
                break

            # ── Telemetria LoRa ───────────────────────────────────────────────
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

                # Jeśli mamy wynik exec — wyślij go PRZED otwarciem okna RX
                if exec_result is not None:
                    lora.send(exec_result)
                    exec_result = None

                raw_cmd = lora.listen(UPLINK_RX_WINDOW_S)
                if raw_cmd:
                    cmd = parse_command(raw_cmd)
                    if cmd:
                        if cmd.get("cmd") == "exec":
                            sh = cmd.get("sh", "")
                            log.info("EXEC: %s", sh)
                            try:
                                proc = subprocess.run(
                                    ["bash", "-c", sh],
                                    capture_output=True, text=True, timeout=8,
                                )
                                exec_result = build_exec_result(
                                    proc.returncode,
                                    proc.stdout.strip(),
                                    proc.stderr.strip(),
                                )
                            except subprocess.TimeoutExpired:
                                exec_result = build_exec_result(
                                    -1, "", "timeout (8s)")
                            except Exception as e:
                                exec_result = build_exec_result(-1, "", str(e))
                        else:
                            apply_command(cmd, buzzer, led)

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
        buzzer.close()
        led.close()
        gps.close()
        lora.close()
        aprs.close()
        power.close()


if __name__ == "__main__":
    main()
