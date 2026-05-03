#!/usr/bin/env python3
"""
StratoSTEAM — Ground station
Receives LoRa telemetry from balloon, forwards to backend.
Handles uplink: buzzer/LED commands + RPi power control via ESP32.
"""
import json
import logging
import sys
import time

from radio import LoRaRX
from uplink import Uplink
from hf_controller import HfController
from command_store import CommandStore
from rpi_power_store import RpiPowerStore
from exec_store import ExecStore
from packet import build_command, build_rpi_power_command, build_exec_command

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/var/log/stratosteam-ground.log"),
    ],
)
log = logging.getLogger("ground")


def main():
    lora      = LoRaRX()
    uplink    = Uplink()
    hf        = HfController()
    commands  = CommandStore()
    rpi_power = RpiPowerStore()
    exec_s    = ExecStore()

    hf.start()
    commands.start()
    rpi_power.start()
    exec_s.start()
    log.info("Ground station listening…")

    try:
        while True:
            raw, rssi, snr = lora.receive(timeout_s=1.0)
            if raw is None:
                continue

            try:
                packet = json.loads(raw.decode())
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                log.warning("Bad packet: %s", e)
                continue

            # Determine source: ESP32 beacon or full RPi telemetry
            from_esp32 = packet.get("src") == "esp32"
            rpi_running = not from_esp32
            rpi_power.report_status(rpi_running)

            if from_esp32:
                log.info(
                    "ESP32 beacon seq=%s lat=%s lon=%s vbat=%s RSSI=%d",
                    packet.get("seq"), packet.get("lat"),
                    packet.get("lon"), packet.get("vbat"), rssi,
                )
                # Forward ESP32 beacon as minimal telemetry so Flutter sees GPS
                uplink.send(packet, rssi, snr)
            else:
                log.info(
                    "RPi telemetry seq=%s RSSI=%d dBm SNR=%.1f dB alt=%.0fm",
                    packet.get("seq"), rssi, snr,
                    (packet.get("gps") or {}).get("alt") or 0,
                )
                uplink.send(packet, rssi, snr)

            # ── Jeśli to wynik exec od rpi-air — przekaż do backendu ─────────
            if packet.get("type") == "exec_result":
                exec_s.post_result(
                    rc=int(packet.get("rc", -1)),
                    out=packet.get("out", ""),
                    err=packet.get("err", ""),
                )
                log.info("Exec result rc=%s out=%r", packet.get("rc"), packet.get("out"))
                continue

            # ── Uplink window: exec > rpi_power > buzzer/led ──────────────────
            sh = exec_s.pop()
            if sh is not None:
                pkt = build_exec_command(sh)
                ok = lora.send_command(pkt)
                log.info("Exec sent sh=%r ok=%s", sh, ok)
            else:
                pwr_cmd = rpi_power.pop()
                if pwr_cmd is not None:
                    pkt = build_rpi_power_command(pwr_cmd)
                    ok = lora.send_command(pkt)
                    log.info("RPi power cmd sent on=%s ok=%s", pwr_cmd, ok)
                else:
                    cmd = commands.pop()
                    if cmd:
                        pkt = build_command(
                            buzzer=bool(cmd.get("buzzer", False)),
                            r=int(cmd.get("led_r", 0)),
                            g=int(cmd.get("led_g", 0)),
                            b=int(cmd.get("led_b", 0)),
                        )
                        ok = lora.send_command(pkt)
                        log.info(
                            "CMD sent ok=%s buzzer=%s led=(%s,%s,%s)",
                            ok, cmd.get("buzzer"),
                            cmd.get("led_r"), cmd.get("led_g"), cmd.get("led_b"),
                        )

    except KeyboardInterrupt:
        log.info("Shutdown")
    finally:
        hf.stop()
        lora.close()


if __name__ == "__main__":
    main()
