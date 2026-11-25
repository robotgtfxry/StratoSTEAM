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

import threading
import requests

from radio import LoRaRX
from uplink import Uplink
from beacon import expand_beacon, has_rpi_data, beacon_to_telemetry
from hf_controller import HfController
from command_store import CommandStore
from rpi_power_store import RpiPowerStore
from exec_store import ExecStore
from camera_store import CameraStore
from espcam_store import EspCamStore
from packet import (
    build_command, build_rpi_power_command, build_exec_command,
    build_photo_command, build_cam_rec_command, build_espcam_power_command,
)
from config import BACKEND_URL, BACKEND_API_KEY

_HF_HEADERS = {"X-API-Key": BACKEND_API_KEY}


def _post_hf_measurement(alt: float, dbfs: float) -> None:
    def _send():
        try:
            requests.post(
                f"{BACKEND_URL}/api/hf/measurement",
                json={"alt": alt, "dbfs": dbfs},
                headers=_HF_HEADERS,
                timeout=5,
            )
        except requests.RequestException as e:
            log.debug("HF measurement upload error: %s", e)
    threading.Thread(target=_send, daemon=True).start()


def _post_espcam_status(ec: list) -> None:
    def _send():
        try:
            requests.post(
                f"{BACKEND_URL}/api/espcam/status",
                json={"ec": ec},
                headers=_HF_HEADERS,
                timeout=5,
            )
        except requests.RequestException as e:
            log.debug("EspCam status upload error: %s", e)
    threading.Thread(target=_send, daemon=True).start()

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
    camera_s  = CameraStore()
    espcam_s  = EspCamStore()

    hf.start()
    commands.start()
    rpi_power.start()
    exec_s.start()
    camera_s.start()
    espcam_s.start()
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

            # ── Chunk obrazu z kamery — przekaż do backendu i pomiń resztę ───
            if packet.get("type") == "img":
                camera_s.post_chunk(packet)
                log.info(
                    "IMG chunk id=%s seq=%s/%s RSSI=%d",
                    packet.get("id"), packet.get("seq"), packet.get("tot"), rssi,
                )
                continue

            # Determine source: ESP32 beacon or full RPi telemetry
            from_esp32 = packet.get("src") == "esp32"
            if from_esp32:
                packet = expand_beacon(packet)
            is_exec_result = packet.get("type") == "exec_result"

            # ── Jeśli to wynik exec od rpi-air — przekaż do backendu ─────────
            # (sprawdzamy PRZED uplink.send aby nie wysyłać exec_result jako telemetrii)
            if is_exec_result:
                exec_s.post_result(
                    rc=int(packet.get("rc", -1)),
                    out=packet.get("out", ""),
                    err=packet.get("err", ""),
                )
                log.info("Exec result rc=%s out=%r", packet.get("rc"), packet.get("out"))
                # NIE robimy continue — otwieramy okno uplink normalnie poniżej

            # beacon ESP32 z danymi czujników = RPi na balonie działa
            rpi_running = has_rpi_data(packet) if from_esp32 else True
            rpi_power.report_status(rpi_running)

            if from_esp32:
                log.info(
                    "ESP32 beacon seq=%s lat=%s lon=%s vbat=%s vbe=%s RSSI=%d",
                    packet.get("seq"), packet.get("lat"),
                    packet.get("lon"), packet.get("vbat"), packet.get("vbe"), rssi,
                )
                uplink.send(beacon_to_telemetry(packet), rssi, snr)

                # Disk info z beacona → backend
                if packet.get("dsku") is not None and packet.get("dskf") is not None:
                    camera_s.post_storage(
                        used_gb=float(packet["dsku"]),
                        free_gb=float(packet["dskf"]),
                    )

                # ESP32-CAM status z beacona → backend
                ec = packet.get("ec")
                if ec and isinstance(ec, list):
                    _post_espcam_status(ec)
                    log.debug("EspCam status forwarded: %s", ec)

                # HF SDR measurement z beacona → backend
                hfdb = packet.get("hfdb")
                if hfdb is not None and hfdb > -999.0:
                    alt = float(packet.get("alt2") or packet.get("alt") or 0.0)
                    _post_hf_measurement(alt=alt, dbfs=float(hfdb))
                    log.info("HF measurement: %.1f dBFS @ %.0f m", hfdb, alt)
            elif not is_exec_result:
                log.info(
                    "RPi telemetry seq=%s RSSI=%d dBm SNR=%.1f dB alt=%.0fm",
                    packet.get("seq"), rssi, snr,
                    (packet.get("gps") or {}).get("alt") or 0,
                )
                uplink.send(packet, rssi, snr)
                # ESP32-CAM status w pakiecie RPi → backend
                ec = packet.get("ec")
                if ec and isinstance(ec, list):
                    _post_espcam_status(ec)
                    log.debug("EspCam status from RPi pkt: %s", ec)

            # ── Uplink window (tylko gdy pakiet pochodzi od RPi) ───────────────
            # ESP32 nie nasłuchuje — komendy tylko do RPi
            if not from_esp32:
                sh = exec_s.pop()
                if sh is not None:
                    pkt = build_exec_command(sh)
                    ok = lora.send_command(pkt)
                    log.info("Exec sent sh=%r ok=%s", sh, ok)
                else:
                    # rpi_power "off" → wyślij do RPi żeby sama się zamknęła
                    pwr_cmd = rpi_power.pop()
                    if pwr_cmd is False:   # tylko "off" ma sens przez LoRa
                        pkt = build_rpi_power_command(False)
                        ok = lora.send_command(pkt)
                        log.info("RPi shutdown cmd sent ok=%s", ok)
                    elif pwr_cmd is True:
                        log.info("RPi power ON requested but RPi already running")
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

                # ── Komendy kamery (ESP32 zawsze słucha, więc nadaj w każdym oknie) ──
                if camera_s.pop_photo():
                    ok = lora.send_command(build_photo_command())
                    log.info("Camera photo cmd sent ok=%s", ok)
                else:
                    rec = camera_s.pop_rec()
                    if rec is not None:
                        ok = lora.send_command(build_cam_rec_command(rec))
                        log.info("Camera rec cmd on=%s sent ok=%s", rec, ok)

                # ── ESP-CAM power ─────────────────────────────────────────────
                cam_on = espcam_s.pop()
                if cam_on is not None:
                    ok = lora.send_command(build_espcam_power_command(cam_on))
                    log.info("EspCam power cmd on=%s ok=%s", cam_on, ok)

            else:
                # ── Okno po beaconie ESP32: jedna komenda na okno ─────────────
                # Pozostałe czekają w swoich kolejkach na następny beacon.
                if exec_s.pop() is not None:
                    log.warning("exec odrzucony — ESP32 nie obsługuje tej komendy")

                if (pwr_cmd := rpi_power.pop()) is not None:
                    ok = lora.send_command(build_rpi_power_command(pwr_cmd))
                    log.info("RPi power cmd → ESP32 on=%s ok=%s", pwr_cmd, ok)
                elif cmd := commands.pop():
                    ok = lora.send_command(build_command(
                        buzzer=bool(cmd.get("buzzer", False)),
                        r=int(cmd.get("led_r", 0)),
                        g=int(cmd.get("led_g", 0)),
                        b=int(cmd.get("led_b", 0)),
                    ))
                    log.info("CMD → ESP32 ok=%s buzzer=%s led=(%s,%s,%s)", ok,
                             cmd.get("buzzer"), cmd.get("led_r"), cmd.get("led_g"), cmd.get("led_b"))
                elif camera_s.pop_photo():
                    ok = lora.send_command(build_photo_command())
                    log.info("Camera photo cmd → ESP32 ok=%s", ok)
                elif (rec := camera_s.pop_rec()) is not None:
                    ok = lora.send_command(build_cam_rec_command(rec))
                    log.info("Camera rec cmd on=%s → ESP32 ok=%s", rec, ok)
                elif (cam_on := espcam_s.pop()) is not None:
                    ok = lora.send_command(build_espcam_power_command(cam_on))
                    log.info("EspCam power cmd on=%s → ESP32 ok=%s", cam_on, ok)

    except KeyboardInterrupt:
        log.info("Shutdown")
    finally:
        hf.stop()
        lora.close()


if __name__ == "__main__":
    main()
