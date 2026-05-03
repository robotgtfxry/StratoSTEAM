#!/usr/bin/env python3
"""
StratoSTEAM — Ground station
Receives LoRa telemetry from balloon, forwards to backend.
After each received packet sends a pending command (buzzer/LED) back to balloon.
"""
import json
import logging
import sys
import time

from radio import LoRaRX
from uplink import Uplink
from hf_controller import HfController
from command_store import CommandStore
from packet import build_command

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
    lora     = LoRaRX()
    uplink   = Uplink()
    hf       = HfController()
    commands = CommandStore()

    hf.start()
    commands.start()
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

            log.info(
                "RX seq=%s RSSI=%d dBm SNR=%.1f dB alt=%.0fm",
                packet.get("seq"), rssi, snr,
                (packet.get("gps") or {}).get("alt") or 0,
            )
            uplink.send(packet, rssi, snr)

            # ── uplink window: send command if one is pending ────
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
