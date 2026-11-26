#!/usr/bin/env python3
"""
StratoSTEAM — Ground station
Receives LoRa telemetry from balloon, forwards to backend.
Handles uplink: buzzer/LED commands + RPi power control via ESP32.
"""
import json
import logging
import os
import sys
import time

import threading
import requests

from radio import LoRaRX
from uplink import Uplink
from beacon import expand_beacon, has_rpi_data, beacon_to_telemetry
from command_store import CommandStore
from rpi_power_store import RpiPowerStore
from exec_store import ExecStore
from local_feed import LOG_DIR, LocalFeed
from mission import Mission
from mission_uplink import MissionUplink
from callsign_store import CallsignStore
from photo_outbox import PhotoOutbox
from photo_rx import PKT_MAGIC, PhotoRx, airtime, choose_sf
from camera_store import CameraStore
from espcam_store import EspCamStore
from packet import (
    build_command, build_rpi_power_command, build_exec_command,
    build_photo_command, build_cam_rec_command, build_espcam_power_command,
    build_buzzer_command, build_callsign_command, build_flight_command, build_raw_command,
)
from config import BACKEND_URL, BACKEND_API_KEY, HF_ENABLED, LORA_SF

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


def receive_burst(lora, photo: PhotoRx, feed: LocalFeed, sf: int, count: int) -> None:
    """Seria pakietów zdjęcia na innym SF. Zawsze wraca na zwykły SF."""
    per_pkt = airtime(sf, 244) + 0.08
    deadline = time.time() + 1.5 + count * per_pkt
    got = 0
    lora.set_sf(sf)
    try:
        while time.time() < deadline and got < count:
            raw, _, _ = lora.receive(timeout_s=0.5)
            if raw and raw[0] == PKT_MAGIC and photo.data(raw) is not None:
                got += 1
            feed.photo_progress(photo.state())
            feed.tick(getattr(lora, "resets", 0))
    finally:
        lora.set_sf(LORA_SF)
    log.info("Zdjęcie id=%s: seria %d/%d na SF%d, razem %d/%d",
             photo.id, got, count, sf, len(photo.parts), photo.n)


def main():
    lora      = LoRaRX()
    uplink    = Uplink()
    commands  = CommandStore()
    rpi_power = RpiPowerStore()
    exec_s    = ExecStore()
    camera_s  = CameraStore()
    espcam_s  = EspCamStore()
    feed      = LocalFeed()      # okno gui_odbior.py + dziennik na karcie
    photo     = PhotoRx()
    mission   = Mission(os.path.join(LOG_DIR, "misja.json"))
    mission_up = MissionUplink()
    callsign  = CallsignStore()
    outbox    = PhotoOutbox(os.path.join(LOG_DIR, "do-wyslania"))   # zdjęcia czekające na internet
    last_snr: float | None = None
    buzzer: list[tuple[bool, int]] = []      # komendy buzzera z okna

    # TODO(HF): do zrobienia — brak filtra, nadajnik wyłączony (HF_ENABLED w config.py).
    # Import tutaj, bo HfController od razu otwiera SPI1, którego bez nadajnika nie ma.
    hf = None
    if HF_ENABLED:
        from hf_controller import HfController
        hf = HfController()
        hf.start()
    else:
        log.info("HF: wyłączone (do zrobienia)")

    commands.start()
    rpi_power.start()
    exec_s.start()
    camera_s.start()
    espcam_s.start()
    mission_up.start()
    callsign.start()
    outbox.start()
    log.info("Ground station listening…")

    try:
        while True:
            for c in feed.commands():
                if c.get("a") == "buzzer":
                    on = bool(c.get("on"))
                    ms = min(max(int(c.get("ms") or 0), 0), 60000) if on else 0
                    # impuls raz; włączenie na stałe i wyłączenie powtórz — łącze bez potwierdzeń
                    buzzer = [(on, ms)] if ms else [(on, 0)] * 2
                    feed.buzzer("czeka na pakiet z balonu")
                else:
                    mission.command(c, time.time())
            if (auto := mission.pop_auto()) is not None:
                feed.set_auto(auto)
            feed.mission(mission.state())
            mission_up.update(mission.state(), feed.auto_on(), feed.last_rx, feed.tcpu, feed.callsign)
            feed.photo_progress(photo.state())
            feed.tick(getattr(lora, "resets", 0))
            raw, rssi, snr = lora.receive(timeout_s=1.0)
            if raw is None:
                continue

            if raw[0] == PKT_MAGIC:         # spóźniony pakiet serii
                photo.data(raw)
                continue
            try:
                packet = json.loads(raw.decode())
                if not isinstance(packet, dict):
                    raise ValueError("nie jest obiektem JSON")
            except ValueError as e:
                log.warning("Bad packet: %s", e)
                feed.bad()
                continue

            # ── Zapowiedź serii zdjęcia ─────────────────────────────────────
            if packet.get("t") == "ph":
                plan = photo.announce(packet)
                if plan:
                    receive_burst(lora, photo, feed, *plan)
                    blob = photo.complete()
                    if blob:
                        log.info("Zdjęcie id=%d komplet: %d B w %.0f s", photo.id, len(blob),
                                 time.time() - photo.started)
                        outbox.add(feed.photo_done(blob))
                continue

            # Determine source: ESP32 beacon or full RPi telemetry
            from_esp32 = packet.get("src") == "esp32"
            if from_esp32:
                packet = expand_beacon(packet)
                last_snr = snr
                if "q" in packet:
                    photo.from_beacon(packet.pop("q"))
                mission.update(packet, time.time())
                feed.packet(packet, rssi, snr)
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
                if HF_ENABLED and hfdb is not None and hfdb > -999.0:
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
                elif buzzer:
                    on, ms = buzzer.pop(0)
                    ok = lora.send_command(build_buzzer_command(on, ms))
                    feed.buzzer(("gra" if on else "wyłączony") + (f" {ms // 1000} s" if ms else ""))
                    log.info("Buzzer on=%s ms=%d → ESP32 ok=%s", on, ms, ok)
                elif (flight := mission.pop_flight()) is not None:
                    ok = lora.send_command(build_flight_command(flight))
                    log.info("Flight cmd on=%s → ESP32 ok=%s", flight, ok)
                elif (cs := callsign.pop(feed.callsign)) is not None:
                    ok = lora.send_command(build_callsign_command(cs))
                    log.info("Znak wywoławczy %s → ESP32 ok=%s (teraz nadaje jako %s)", cs, ok, feed.callsign)
                elif (pc := photo.command(choose_sf(last_snr))) is not None:
                    ok = lora.send_command(build_raw_command(pc))
                    log.info("Zdjęcie %s → ESP32 ok=%s", pc, ok)
                elif not photo.receiving and (feed.pop_photo() or camera_s.pop_photo()):
                    sf = choose_sf(last_snr)
                    ok = lora.send_command(build_photo_command(sf))
                    log.info("Camera photo cmd sf=%d → ESP32 ok=%s", sf, ok)
                elif (rec := camera_s.pop_rec()) is not None:
                    ok = lora.send_command(build_cam_rec_command(rec))
                    log.info("Camera rec cmd on=%s → ESP32 ok=%s", rec, ok)
                elif (cam_on := espcam_s.pop()) is not None:
                    ok = lora.send_command(build_espcam_power_command(cam_on))
                    log.info("EspCam power cmd on=%s → ESP32 ok=%s", cam_on, ok)

    except KeyboardInterrupt:
        log.info("Shutdown")
    finally:
        if hf:
            hf.stop()
        lora.close()


if __name__ == "__main__":
    main()
