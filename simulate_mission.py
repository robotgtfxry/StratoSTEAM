#!/usr/bin/env python3
"""
simulate_mission.py — symulator misji balonowej StratoSTEAM

Symuluje pełną misję: start, wznoszenie, apogeum, opadanie, lądowanie.
Wysyła dane telemetryczne bezpośrednio do backendu co INTERVAL sekund.

Uruchomienie:
    pip install requests
    python simulate_mission.py

    # Inny serwer lub klucz:
    python simulate_mission.py --url http://frog02.mikr.us:21124 --key change-me-in-production

    # Szybsza symulacja (co 1s zamiast 5s):
    python simulate_mission.py --interval 1 --speed 5
"""

import argparse
import math
import random
import sys
import time
import requests

# ── Parametry misji ────────────────────────────────────────────────────────────
LAUNCH_LAT  =  52.2297   # Warszawa
LAUNCH_LON  =  21.0122
APOGEUM_ALT = 32000      # m
ASCENT_RATE =  5.0       # m/s podczas wznoszenia
DESCENT_RATE = 8.0       # m/s podczas opadania (szybciej — urwany balon)
DRIFT_LAT   =  0.00002   # dryfowanie na wschód
DRIFT_LON   =  0.00003

# ── Kolory etapów (do logów) ───────────────────────────────────────────────────
RESET = "\033[0m"
GREEN = "\033[92m"
CYAN  = "\033[96m"
YELLOW= "\033[93m"
RED   = "\033[91m"
BOLD  = "\033[1m"


def phase_color(phase: str) -> str:
    return {
        "PREFLIGHT": CYAN,
        "ASCENT":    GREEN,
        "APOGEUM":   YELLOW,
        "DESCENT":   YELLOW,
        "LANDED":    RED,
    }.get(phase, RESET)


def simulate_physics(t: float, alt: float, phase: str):
    """Zwraca (lat, lon, alt, spd, hdg, phase) dla danej chwili."""

    if phase == "PREFLIGHT":
        return alt, phase

    if phase == "ASCENT":
        alt += ASCENT_RATE
        if alt >= APOGEUM_ALT:
            phase = "APOGEUM"
    elif phase == "APOGEUM":
        phase = "DESCENT"
    elif phase == "DESCENT":
        alt -= DESCENT_RATE
        if alt <= 0:
            alt = 0
            phase = "LANDED"

    return alt, phase


def bme_model(alt: float):
    """Temperatura i ciśnienie wg modelu ISA."""
    if alt < 11000:
        temp = 15.0 - 0.0065 * alt
        pres = 1013.25 * (1 - 0.0065 * alt / 288.15) ** 5.2561
    elif alt < 20000:
        temp = -56.5
        pres = 226.32 * math.exp(-0.0001577 * (alt - 11000))
    else:
        temp = -56.5 + 0.001 * (alt - 20000)
        pres = 54.75 * math.exp(-0.0001262 * (alt - 20000))
    hum = max(0, 60 - alt / 500)  # wilgotność spada z wysokością
    return round(temp + random.uniform(-0.2, 0.2), 2), \
           round(pres + random.uniform(-0.1, 0.1), 2), \
           round(hum  + random.uniform(-1, 1), 1)


def imu_model(phase: str, t: float):
    """Symuluje pochylenie balonu."""
    sway = math.sin(t * 0.3) * 5
    if phase in ("DESCENT", "LANDED"):
        return (round(sway * 2 + random.uniform(-1, 1), 1),
                round(sway   + random.uniform(-1, 1), 1),
                round(t * 2 % 360, 1))
    return (round(sway + random.uniform(-0.5, 0.5), 1),
            round(sway * 0.5 + random.uniform(-0.5, 0.5), 1),
            round(t * 0.5 % 360, 1))


def pwr_model(alt: float):
    """Napięcie baterii spada z czasem i temperaturą."""
    base_v = 4.15 - alt / 200000
    current = 320 + random.uniform(-20, 20)
    voltage = round(base_v + random.uniform(-0.02, 0.02), 3)
    return voltage, round(current, 1), round(voltage * current, 1)


def build_packet(seq, lat, lon, alt, phase, t):
    temp, pres, hum = bme_model(alt)
    roll, pitch, yaw = imu_model(phase, t)
    voltage, current, power = pwr_model(alt)
    spd = ASCENT_RATE * 3.6 if phase == "ASCENT" else \
          DESCENT_RATE * 3.6 if phase == "DESCENT" else 0.0
    rssi = int(-80 - alt / 2000 + random.uniform(-5, 5))
    snr  = round(8.0 - alt / 8000 + random.uniform(-1, 1), 1)

    return {
        "seq":  seq,
        "ts":   int(time.time()),
        "rssi": rssi,
        "snr":  snr,
        "gps": {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "alt": round(alt, 1),
            "spd": round(spd, 1),
            "hdg": round((t * 5) % 360, 1),
            "sat": 12 if phase != "PREFLIGHT" else random.randint(0, 5),
            "fix": phase != "PREFLIGHT",
        },
        "bme": {"temperature_c": temp, "humidity_pct": hum, "pressure_hpa": pres},
        "ms":  {"temperature_c": round(temp - 1, 2),
                "pressure_hpa": round(pres - 0.5, 2),
                "altitude_m":   round(alt + random.uniform(-2, 2), 1)},
        "imu": {"roll_deg": roll, "pitch_deg": pitch, "yaw_deg": yaw,
                "accel_x": round(random.uniform(-0.1, 0.1), 3),
                "accel_y": round(random.uniform(-0.1, 0.1), 3),
                "accel_z": round(9.81 + random.uniform(-0.05, 0.05), 3)},
        "pwr": {"voltage_v": voltage, "current_ma": current, "power_mw": power},
    }


def send(url: str, key: str, packet: dict) -> bool:
    try:
        r = requests.post(
            f"{url}/api/telemetry",
            json=packet,
            headers={"X-API-Key": key, "Content-Type": "application/json"},
            timeout=5,
        )
        return r.status_code == 201
    except Exception as e:
        print(f"  {RED}HTTP error: {e}{RESET}")
        return False


def main():
    parser = argparse.ArgumentParser(description="StratoSTEAM mission simulator")
    parser.add_argument("--url",      default="http://frog02.mikr.us:21124",
                        help="Backend URL")
    parser.add_argument("--key",      default="change-me-in-production",
                        help="API key")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="Sekundy między pakietami (domyślnie 5)")
    parser.add_argument("--speed",    type=float, default=1.0,
                        help="Mnożnik prędkości symulacji (domyślnie 1)")
    parser.add_argument("--preflight",type=int,   default=3,
                        help="Liczba pakietów PREFLIGHT przed startem")
    args = parser.parse_args()

    print(f"\n{BOLD}{'='*55}")
    print(f"  StratoSTEAM — Symulator misji balonowej")
    print(f"{'='*55}{RESET}")
    print(f"  Backend : {args.url}")
    print(f"  Interval: {args.interval}s  (speed x{args.speed})")
    print(f"  Apogeum : {APOGEUM_ALT}m")
    print(f"  Start   : {LAUNCH_LAT}°N {LAUNCH_LON}°E\n")

    # Sprawdź połączenie
    try:
        r = requests.get(f"{args.url}/api/telemetry/latest", timeout=5)
        print(f"  {GREEN}✓ Backend odpowiada (status {r.status_code}){RESET}\n")
    except Exception as e:
        print(f"  {RED}✗ Brak połączenia z backendem: {e}{RESET}")
        sys.exit(1)

    seq   = 0
    alt   = 0.0
    lat   = LAUNCH_LAT
    lon   = LAUNCH_LON
    phase = "PREFLIGHT"
    t     = 0.0
    preflight_count = 0

    print(f"  {CYAN}Faza PREFLIGHT — {args.preflight} pakietów...{RESET}\n")

    try:
        while True:
            # Aktualizuj fizykę
            if phase == "PREFLIGHT":
                preflight_count += 1
                if preflight_count > args.preflight:
                    phase = "ASCENT"
                    print(f"\n  {GREEN}{BOLD}🚀 START! Wznoszenie...{RESET}\n")
            else:
                alt, phase = simulate_physics(t, alt, phase)
                lat += DRIFT_LAT * args.speed
                lon += DRIFT_LON * args.speed

            # Buduj i wyślij pakiet
            pkt = build_packet(seq, lat, lon, alt, phase, t)
            ok  = send(args.url, args.key, pkt)

            # Log
            col = phase_color(phase)
            status_icon = "✓" if ok else "✗"
            print(
                f"  {col}[{phase:10s}]{RESET} "
                f"seq={seq:4d}  alt={alt:7.0f}m  "
                f"lat={lat:.5f}  lon={lon:.5f}  "
                f"temp={pkt['bme']['temperature_c']:6.1f}°C  "
                f"vbat={pkt['pwr']['voltage_v']:.3f}V  "
                f"RSSI={pkt['rssi']}dBm  "
                f"{'✓' if ok else RED+'✗'+RESET}"
            )

            if phase == "LANDED":
                print(f"\n  {RED}{BOLD}🎯 Lądowanie! alt={alt:.0f}m{RESET}")
                print(f"  Pozycja lądowania: {lat:.6f}°N {lon:.6f}°E")
                print(f"  Całkowity czas: {seq * args.interval:.0f}s")
                print(f"\n  Kontynuuję wysyłanie danych z ziemi (Ctrl+C aby zatrzymać)...\n")

            seq += 1
            t   += args.interval * args.speed
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n\n  {YELLOW}Symulacja zatrzymana. Wysłano {seq} pakietów.{RESET}\n")


if __name__ == "__main__":
    main()
