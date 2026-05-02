#!/usr/bin/env python3
"""
StratoSTEAM — Ground station
Receives LoRa packets and forwards them to the backend server.
"""
import json
import logging
import sys
import time

from radio import LoRaRX
from uplink import Uplink

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
    lora   = LoRaRX()
    uplink = Uplink()
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

    except KeyboardInterrupt:
        log.info("Shutdown")
    finally:
        lora.close()


if __name__ == "__main__":
    main()
