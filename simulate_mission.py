#!/usr/bin/env python3
"""
simulate_mission.py — symulator misji balonowej StratoSTEAM

Symuluje pełną misję: start → wznoszenie → apogeum → opadanie → lądowanie.
Wysyła dane telemetryczne do backendu co INTERVAL sekund.
Symuluje też pomiary HF SDR (dBFS vs wysokość) co SDR_INTERVAL pakietów.

Uruchomienie:
    pip install requests
    python simulate_mission.py

    # Inny serwer lub klucz:
    python simulate_mission.py --url http://frog02.mikr.us:21124 --key change-me-in-production

    # Szybsza symulacja:
    python simulate_mission.py --interval 1 --speed 5

    # Lokalny backend (domyślnie):
    python simulate_mission.py --url http://localhost:8000
"""

import argparse
import math
import random
import sys
import time
import requests

# ── Parametry misji ────────────────────────────────────────────────────────────
LAUNCH_LAT   =  52.2297   # Warszawa
LAUNCH_LON   =  21.0122
APOGEUM_ALT  = 32_000     # m
ASCENT_RATE  =  5.0       # m/s
DESCENT_RATE =  8.0       # m/s (szybciej — urwany balon)
DRIFT_LAT    =  0.00002   # dryfowanie na wschód (°/pakiet)
DRIFT_LON    =  0.00003

HF_FREQ_HZ   = 7_100_000  # Hz — symulowany nadajnik HF (pasmo 40m)
SDR_INTERVAL = 2           # co ile pakietów telemetrii symulujemy pomiar SDR

# ── Kolory terminala ──────────────────────────────────────────────────────────
RESET  = "\033[0m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
RED    = "\033[91m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

PHASE_COLOR = {
    "PREFLIGHT": CYAN,
    "ASCENT":    GREEN,
    "APOGEUM":   YELLOW,
    "DESCENT":   YELLOW,
    "LANDED":    RED,
}


# ── Modele fizyczne ───────────────────────────────────────────────────────────

def update_physics(alt: float, phase: str) -> tuple[float, str]:
    if phase == "ASCENT":
        alt += ASCENT_RATE
        if alt >= APOGEUM_ALT:
            phase = "APOGEUM"
    elif phase == "APOGEUM":
        phase = "DESCENT"
    elif phase == "DESCENT":
        alt -= DESCENT_RATE
        if alt <= 0:
            alt = 0.0
            phase = "LANDED"
    return alt, phase


def bme_model(alt: float) -> tuple[float, float, float]:
    """Temperatura, ciśnienie, wilgotność wg modelu ISA."""
    if alt < 11_000:
        temp = 15.0 - 0.0065 * alt
        pres = 1013.25 * (1 - 0.0065 * alt / 288.15) ** 5.2561
    elif alt < 20_000:
        temp = -56.5
        pres = 226.32 * math.exp(-0.0001577 * (alt - 11_000))
    else:
        temp = -56.5 + 0.001 * (alt - 20_000)
        pres = 54.75 * math.exp(-0.0001262 * (alt - 20_000))
    hum = max(0.0, 60.0 - alt / 500.0)
    return (round(temp + random.gauss(0, 0.15), 2),
            round(pres + random.gauss(0, 0.08), 2),
            round(hum  + random.gauss(0, 0.5),  1))


def imu_model(phase: str, t: float) -> tuple[float, float, float]:
    """Roll, pitch, yaw — kołysanie balonu."""
    sway = math.sin(t * 0.3) * 5
    scale = 2.0 if phase in ("DESCENT", "LANDED") else 1.0
    return (round(sway * scale + random.gauss(0, 0.4), 1),
            round(sway * 0.5 * scale + random.gauss(0, 0.4), 1),
            round(t * 0.5 % 360, 1))


def pwr_model(alt: float) -> tuple[float, float, float]:
    """Napięcie baterii spada z czasem i temperaturą."""
    voltage = round(4.15 - alt / 200_000 + random.gauss(0, 0.01), 3)
    current = round(320 + random.gauss(0, 12), 1)
    return voltage, current, round(voltage * current, 1)


def strain_model(alt: float, phase: str, t: float) -> float:
    """
    Siła liny balonu [g].
    - Preflight/Ascent: duże napięcie (balon ciągnie w górę)
    - Wysokie altitude: mniejsze (rozrzedzone powietrze, mniejszy opór)
    - Apogeum/Descent: gwałtowny spadek po pęknięciu, potem naciąg od spadochronu
    - Landed: blisko zera
    """
    if phase == "PREFLIGHT":
        return round(900 + random.gauss(0, 30), 1)
    elif phase == "ASCENT":
        base = max(150, 850 - alt * 0.02)
        sway = math.sin(t * 0.2) * 40
        return round(base + sway + random.gauss(0, 20), 1)
    elif phase == "APOGEUM":
        return round(60 + random.gauss(0, 10), 1)
    elif phase == "DESCENT":
        base = 350 + alt * 0.004   # spadochron: napięcie rośnie z prędkością
        return round(base + random.gauss(0, 30), 1)
    else:  # LANDED
        return round(max(0, 20 + random.gauss(0, 8)), 1)


def hf_dbfs_model(alt: float) -> float:
    """
    Symulacja siły sygnału HF odbitego od jonosfery [dBFS].
    - Do ~5km: słaby sygnał (direct wave tłumiony przez odległość)
    - 5-15km: wzrost (lepszy kąt refleksji od warstwy E jonosfery)
    - >20km: plateau z fluktuacjami (blisko warstwy refleksji)
    """
    if alt < 2_000:
        base = -85.0
    elif alt < 8_000:
        base = -85.0 + (alt - 2_000) / 600.0 * 3.0
    elif alt < 20_000:
        base = -55.0 + math.sin(alt / 3_000) * 8.0
    else:
        base = -48.0 + math.sin(alt / 1_500) * 12.0
    return round(base + random.gauss(0, 1.5), 1)


# ── Budowanie pakietów ────────────────────────────────────────────────────────

def build_telemetry(seq: int, lat: float, lon: float, alt: float,
                    phase: str, t: float) -> dict:
    temp, pres, hum = bme_model(alt)
    roll, pitch, yaw = imu_model(phase, t)
    voltage, current, power = pwr_model(alt)
    strain = strain_model(alt, phase, t)
    spd = (ASCENT_RATE if phase == "ASCENT" else
           DESCENT_RATE if phase == "DESCENT" else 0.0) * 3.6
    rssi = int(-80 - alt / 2_000 + random.gauss(0, 3))
    snr  = round(8.0 - alt / 8_000 + random.gauss(0, 0.8), 1)

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
            "hdg": round(t * 5 % 360, 1),
            "sat": 12 if phase != "PREFLIGHT" else random.randint(0, 5),
            "fix": phase != "PREFLIGHT",
        },
        "bme": {
            "temperature_c": temp,
            "humidity_pct":  hum,
            "pressure_hpa":  pres,
        },
        "ms": {
            "temperature_c": round(temp - 1.0 + random.gauss(0, 0.1), 2),
            "pressure_hpa":  round(pres - 0.5 + random.gauss(0, 0.05), 2),
            "altitude_m":    round(alt  + random.gauss(0, 1.5), 1),
        },
        "imu": {
            "roll_deg":  roll,
            "pitch_deg": pitch,
            "yaw_deg":   yaw,
            "accel_x":   round(random.gauss(0, 0.08), 3),
            "accel_y":   round(random.gauss(0, 0.08), 3),
            "accel_z":   round(9.81 + random.gauss(0, 0.03), 3),
        },
        "pwr": {
            "voltage_v":  voltage,
            "current_ma": current,
            "power_mw":   power,
        },
        "strain_g": strain,
    }


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def post_telemetry(url: str, key: str, packet: dict) -> bool:
    try:
        r = requests.post(
            f"{url}/api/telemetry",
            json=packet,
            headers={"X-API-Key": key, "Content-Type": "application/json"},
            timeout=5,
        )
        return r.status_code == 201
    except Exception as e:
        print(f"  {RED}Telemetry error: {e}{RESET}")
        return False


def post_hf_measurement(url: str, key: str, alt: float, dbfs: float) -> bool:
    try:
        r = requests.post(
            f"{url}/api/hf/measurement",
            json={"alt": alt, "dbfs": dbfs},
            headers={"X-API-Key": key, "Content-Type": "application/json"},
            timeout=5,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"  {RED}HF error: {e}{RESET}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="StratoSTEAM mission simulator")
    parser.add_argument("--url",       default="http://localhost:8000",
                        help="Backend URL (domyślnie: http://localhost:8000)")
    parser.add_argument("--key",       default="change-me-in-production",
                        help="API key")
    parser.add_argument("--interval",  type=float, default=5.0,
                        help="Sekundy między pakietami (domyślnie: 5)")
    parser.add_argument("--speed",     type=float, default=1.0,
                        help="Mnożnik prędkości fizyki (domyślnie: 1)")
    parser.add_argument("--preflight", type=int,   default=3,
                        help="Liczba pakietów PREFLIGHT przed startem")
    parser.add_argument("--no-hf",     action="store_true",
                        help="Wyłącz symulację pomiarów HF SDR")
    args = parser.parse_args()

    print(f"\n{BOLD}{'─'*58}")
    print("  StratoSTEAM — Symulator misji balonowej")
    print(f"{'─'*58}{RESET}")
    print(f"  Backend  : {args.url}")
    print(f"  Interval : {args.interval}s  ×speed {args.speed}")
    print(f"  Apogeum  : {APOGEUM_ALT} m")
    print(f"  Start    : {LAUNCH_LAT}°N {LAUNCH_LON}°E")
    print(f"  HF SDR   : {'OFF (--no-hf)' if args.no_hf else f'co {SDR_INTERVAL} pakiety'}")
    print(f"{'─'*58}\n")

    # Sprawdź połączenie
    try:
        r = requests.get(f"{args.url}/api/telemetry/latest", timeout=5)
        print(f"  {GREEN}✓ Backend odpowiada ({r.status_code}){RESET}\n")
    except Exception as e:
        print(f"  {RED}✗ Brak połączenia z backendem: {e}{RESET}")
        sys.exit(1)

    seq   = 0
    alt   = 0.0
    lat   = LAUNCH_LAT
    lon   = LAUNCH_LON
    phase = "PREFLIGHT"
    t     = 0.0
    preflight_sent = 0

    print(f"  {CYAN}Faza PREFLIGHT — {args.preflight} pakiet(ów)...{RESET}\n")

    try:
        while True:
            # ── Aktualizuj fizykę ────────────────────────────────────────────
            if phase == "PREFLIGHT":
                preflight_sent += 1
                if preflight_sent > args.preflight:
                    phase = "ASCENT"
                    print(f"\n  {GREEN}{BOLD}>>> START! Wznoszenie...{RESET}\n")
            else:
                alt, phase = update_physics(alt, phase)
                lat += DRIFT_LAT * args.speed
                lon += DRIFT_LON * args.speed

            # ── Telemetria ───────────────────────────────────────────────────
            pkt = build_telemetry(seq, lat, lon, alt, phase, t)
            ok  = post_telemetry(args.url, args.key, pkt)

            col = PHASE_COLOR.get(phase, RESET)
            sg  = pkt["strain_g"]
            print(
                f"  {col}[{phase:10s}]{RESET}"
                f"  seq={seq:4d}"
                f"  alt={alt:7.0f}m"
                f"  T={pkt['bme']['temperature_c']:6.1f}°C"
                f"  P={pkt['bme']['pressure_hpa']:7.2f}hPa"
                f"  V={pkt['pwr']['voltage_v']:.3f}V"
                f"  sg={sg:6.0f}g"
                f"  RSSI={pkt['rssi']:4d}dBm"
                f"  {'✓' if ok else RED+'✗'+RESET}"
            )

            # ── HF SDR co SDR_INTERVAL pakietów ─────────────────────────────
            if not args.no_hf and seq % SDR_INTERVAL == 0:
                dbfs = hf_dbfs_model(alt)
                hf_ok = post_hf_measurement(args.url, args.key, alt, dbfs)
                print(f"  {DIM}  └─ HF {dbfs:+.1f} dBFS @ {alt:.0f}m"
                      f"  {'✓' if hf_ok else '✗'}{RESET}")

            # ── Koniec misji ─────────────────────────────────────────────────
            if phase == "LANDED" and seq > args.preflight:
                print(f"\n  {RED}{BOLD}>>> LĄDOWANIE! alt={alt:.0f}m{RESET}")
                print(f"  Pozycja: {lat:.6f}°N {lon:.6f}°E")
                print(f"  Czas lotu: {seq * args.interval:.0f}s")
                print(f"\n  {DIM}Kontynuuję pakiety z ziemi (Ctrl+C = stop)...{RESET}\n")

            seq += 1
            t   += args.interval * args.speed
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print(f"\n\n  {YELLOW}Symulacja zatrzymana — wysłano {seq} pakietów.{RESET}\n")


if __name__ == "__main__":
    main()
