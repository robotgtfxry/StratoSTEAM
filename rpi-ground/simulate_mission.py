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
import base64
import io
import math
import random
import struct
import sys
import time
import threading
import os
import requests

try:
    from config import BACKEND_URL as _DEFAULT_URL, BACKEND_API_KEY as _DEFAULT_KEY
except ImportError:
    _DEFAULT_URL = "http://frog02.mikr.us:21124"
    _DEFAULT_KEY = "change-me-in-production"


def _has_display() -> bool:
    if sys.platform == "win32":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

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


def strain_model(alt: float, phase: str, t: float) -> list[float]:
    """
    Siły liny balonu [g] dla 4 tensometrów (przód-lewy, przód-prawy, tył-lewy, tył-prawy).
    Każdy kanał ma lekko różną wartość bazową i niezależny szum.
    """
    offsets = [0, 30, -20, 15]   # offsety montażowe każdego czujnika [g]
    if phase == "PREFLIGHT":
        base = 900.0
    elif phase == "ASCENT":
        base = max(150.0, 850.0 - alt * 0.02) + math.sin(t * 0.2) * 40
    elif phase == "APOGEUM":
        base = 60.0
    elif phase == "DESCENT":
        base = 350.0 + alt * 0.004
    else:  # LANDED
        base = 20.0
    return [round(max(0, base + o + random.gauss(0, 18)), 1) for o in offsets]


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
    sg = strain_model(alt, phase, t)
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
        "strain_g0": sg[0],
        "strain_g1": sg[1],
        "strain_g2": sg[2],
        "strain_g3": sg[3],
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


# ── Symulacja kamery ─────────────────────────────────────────────────────────

PHOTO_INTERVAL_PKT = 20   # co ile pakietów telemetrii wysyłamy zdjęcie
CHUNK_SIZE         = 2048  # bajty na chunk


def _make_test_jpeg(alt: float, phase: str, seq: int) -> bytes:
    """
    Generuje testowy obrazek JPEG (160×120) bez zewnętrznych bibliotek.
    Używa minimalnego JPEG z gradient-nieba i tekstem.
    Jeśli PIL jest dostępny — używa go dla ładniejszego obrazka.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        w, h = 320, 240
        img = Image.new("RGB", (w, h))
        draw = ImageDraw.Draw(img)

        # gradient nieba: kolor zależy od fazy/wysokości
        if phase in ("PREFLIGHT", "LANDED"):
            sky_top = (100, 150, 200)
            sky_bot = (180, 200, 220)
        elif phase == "ASCENT":
            t = min(alt / 32000, 1.0)
            sky_top = (int(30 * (1 - t)), int(80 * (1 - t)), int(180 - 100 * t))
            sky_bot = (int(100 * (1 - t)), int(150 * (1 - t)), int(220 - 80 * t))
        else:  # APOGEUM / DESCENT
            sky_top = (5, 10, 40)
            sky_bot = (20, 40, 100)

        for y in range(h):
            r = int(sky_top[0] + (sky_bot[0] - sky_top[0]) * y / h)
            g = int(sky_top[1] + (sky_bot[1] - sky_top[1]) * y / h)
            b = int(sky_top[2] + (sky_bot[2] - sky_top[2]) * y / h)
            draw.line([(0, y), (w, y)], fill=(r, g, b))

        # "ziemia" na dole
        if phase in ("PREFLIGHT", "LANDED") or alt < 5000:
            horizon = int(h * 0.75)
            draw.rectangle([(0, horizon), (w, h)], fill=(60, 100, 40))

        # tekst
        lines = [
            f"StratoSTEAM SIM",
            f"Phase: {phase}",
            f"Alt:   {alt:.0f} m",
            f"Seq:   {seq}",
        ]
        for i, line in enumerate(lines):
            draw.text((8, 6 + i * 14), line, fill=(255, 255, 255))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return buf.getvalue()

    except ImportError:
        pass

    # Fallback: minimalny valid JPEG 4×4 px (stały pattern, ~600B)
    # Kodujemy prosty JPEG ręcznie jako małą bitmapę
    return _minimal_jpeg(alt, phase, seq)


def _minimal_jpeg(alt: float, phase: str, seq: int) -> bytes:
    """Zwraca minimalny JPEG zakodowany bez PIL — używa struktury JFIF."""
    # Tworzymy obrazek 16x16 PPM → konwertujemy do JPEG przez struct
    # Najprościej: zwróćmy predefiniowany 1x1 JPEG z odpowiednim kolorem
    # Kolor zależy od fazy: niebieskie=wznoszenie, czarne=apogeum, zielone=ziemia
    if phase in ("PREFLIGHT", "LANDED"):
        r, g, b = 80, 120, 60
    elif phase == "ASCENT":
        t = min(alt / 32000.0, 1.0)
        r, g, b = int(30 * (1 - t)), int(100 * (1 - t)), int(200 - 100 * t)
    else:
        r, g, b = 10, 10, 50

    # Minimalny JPEG 1x1 z danym kolorem YCbCr
    # Y  = 0.299R + 0.587G + 0.114B
    # Cb = 128 - 0.168736R - 0.331264G + 0.5B
    # Cr = 128 + 0.5R - 0.418688G - 0.081312B
    Y  = int(0.299 * r + 0.587 * g + 0.114 * b)
    Cb = int(128 - 0.168736 * r - 0.331264 * g + 0.5 * b)
    Cr = int(128 + 0.5 * r - 0.418688 * g - 0.081312 * b)

    # Prebuilt minimal JPEG skeleton (1x1 pixel, quantization Q50)
    # Source: https://github.com/nicowillis/images/1x1.jpg structure
    jpeg = (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t'
        b'\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a'
        b'\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1e'
        b'\xc7\xeb<\xe3'
        + bytes([Y, Cb, Cr]) +
        b'\xff\xd9'
    )
    # To nie jest valid JPEG — użyjmy PNG 1x1 które jest prostsze do ręcznego kodowania
    # PNG: sygnatura + IHDR + IDAT + IEND
    def png_1x1(r, g, b):
        import zlib
        def chunk(name, data):
            c = name + data
            return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
        sig   = b'\x89PNG\r\n\x1a\n'
        ihdr  = chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
        raw   = b'\x00' + bytes([r, g, b])
        idat  = chunk(b'IDAT', zlib.compress(raw))
        iend  = chunk(b'IEND', b'')
        return sig + ihdr + idat + iend
    return png_1x1(r, g, b)


def post_camera_photo(url: str, key: str, alt: float, phase: str, img_id: int,
                      seq_tel: int, log_fn) -> bool:
    """Generuje testowy obrazek i wysyła go w chunkach do backendu."""
    jpeg = _make_test_jpeg(alt, phase, seq_tel)
    chunks = [jpeg[i:i + CHUNK_SIZE] for i in range(0, len(jpeg), CHUNK_SIZE)]
    total = len(chunks)
    ok_count = 0
    for i, chunk in enumerate(chunks):
        payload = {
            "type":  "img",
            "id":    img_id,
            "seq":   i,
            "tot":   total,
            "data":  base64.b64encode(chunk).decode("ascii"),
        }
        try:
            r = requests.post(
                f"{url}/api/camera/chunk",
                json=payload,
                headers={"X-API-Key": key},
                timeout=5,
            )
            if r.status_code == 200:
                ok_count += 1
        except Exception as e:
            log_fn(f"  └─ CAM chunk {i} error: {e}")
            return False
    log_fn(f"  └─ CAM img#{img_id}  {len(jpeg)}B  {total} chunks  "
           f"{'OK' if ok_count == total else f'{ok_count}/{total}'}")
    return ok_count == total


def post_storage(url: str, key: str, seq: int) -> None:
    """Wysyła symulowany stan dysku."""
    used = round(seq * 0.0004, 2)   # ~0.4MB na zdjęcie
    free = round(max(0, 28.0 - used), 2)
    try:
        requests.post(
            f"{url}/api/camera/storage",
            json={"used_gb": used, "free_gb": free},
            headers={"X-API-Key": key},
            timeout=3,
        )
    except Exception:
        pass


# ── Logika symulacji (wspólna dla CLI i GUI) ──────────────────────────────────

def run_simulation(args, log_fn, stop_event):
    """Uruchamia symulację. log_fn(str) — callback do wypisywania. stop_event — threading.Event."""
    log_fn(f"Backend  : {args['url']}")
    log_fn(f"Interval : {args['interval']}s  ×speed {args['speed']}")
    log_fn(f"Apogeum  : {args['apogeum']}m  Preflight: {args['preflight']} pkt")
    log_fn(f"Start    : {args['lat']}°N {args['lon']}°E")
    log_fn("─" * 50)

    try:
        r = requests.get(f"{args['url']}/api/telemetry/latest", timeout=5)
        log_fn(f"✓ Backend odpowiada ({r.status_code})")
    except Exception as e:
        log_fn(f"✗ Brak połączenia: {e}")
        return

    seq   = 0
    alt   = 0.0
    lat   = args["lat"]
    lon   = args["lon"]
    phase = "PREFLIGHT"
    t     = 0.0
    preflight_sent = 0
    apogeum = args["apogeum"]

    log_fn(f"Faza PREFLIGHT — {args['preflight']} pakiet(ów)...")

    while not stop_event.is_set():
        if phase == "PREFLIGHT":
            preflight_sent += 1
            if preflight_sent > args["preflight"]:
                phase = "ASCENT"
                log_fn(">>> START! Wznoszenie...")
        else:
            # inline update_physics z dynamicznym apogeum
            if phase == "ASCENT":
                alt += ASCENT_RATE * args["speed"]
                if alt >= apogeum:
                    phase = "APOGEUM"
            elif phase == "APOGEUM":
                phase = "DESCENT"
            elif phase == "DESCENT":
                alt -= DESCENT_RATE * args["speed"]
                if alt <= 0:
                    alt = 0.0
                    phase = "LANDED"
            lat += DRIFT_LAT * args["speed"]
            lon += DRIFT_LON * args["speed"]

        pkt = build_telemetry(seq, lat, lon, alt, phase, t)
        ok  = post_telemetry(args["url"], args["key"], pkt)
        sgs = [pkt[f"strain_g{i}"] for i in range(4)]
        log_fn(
            f"[{phase:10s}]  seq={seq:4d}  alt={alt:7.0f}m"
            f"  T={pkt['bme']['temperature_c']:5.1f}°C"
            f"  V={pkt['pwr']['voltage_v']:.3f}V"
            f"  {'OK' if ok else 'ERR'}"
        )

        if not args["no_hf"] and seq % SDR_INTERVAL == 0:
            dbfs = hf_dbfs_model(alt)
            hf_ok = post_hf_measurement(args["url"], args["key"], alt, dbfs)
            log_fn(f"  └─ HF {dbfs:+.1f} dBFS @ {alt:.0f}m  {'OK' if hf_ok else 'ERR'}")

        if seq % PHOTO_INTERVAL_PKT == 0:
            img_id = seq // PHOTO_INTERVAL_PKT
            post_camera_photo(args["url"], args["key"], alt, phase, img_id, seq, log_fn)
            post_storage(args["url"], args["key"], img_id)

        if phase == "LANDED" and seq > args["preflight"]:
            log_fn(f">>> LĄDOWANIE! {lat:.6f}°N {lon:.6f}°E  t={seq * args['interval']:.0f}s")
            log_fn("Kontynuuję pakiety z ziemi (Stop = zatrzymaj)...")

        seq += 1
        t   += args["interval"] * args["speed"]
        stop_event.wait(args["interval"])

    log_fn(f"Symulacja zatrzymana — wysłano {seq} pakietów.")


# ── GUI Tk ────────────────────────────────────────────────────────────────────

def run_gui():
    import tkinter as tk
    from tkinter import ttk, scrolledtext

    root = tk.Tk()
    root.title("StratoSTEAM — Symulator misji")
    root.resizable(False, False)

    stop_event = threading.Event()
    sim_thread = [None]

    # ── Parametry ──
    frm = ttk.LabelFrame(root, text="Parametry symulacji", padding=8)
    frm.grid(row=0, column=0, padx=10, pady=8, sticky="ew")

    fields = [
        ("Backend URL",     "url",       _DEFAULT_URL,  30),
        ("API Key",         "key",       _DEFAULT_KEY,  20),
        ("Interval (s)",    "interval",  "5.0",         6),
        ("Prędkość (×)",    "speed",     "1.0",         6),
        ("Apogeum (m)",     "apogeum",   "32000",       8),
        ("Preflight (pkt)", "preflight", "3",           6),
        ("Lat start (°N)",  "lat",       str(LAUNCH_LAT), 10),
        ("Lon start (°E)",  "lon",       str(LAUNCH_LON), 10),
    ]

    entries = {}
    for i, (label, key, default, width) in enumerate(fields):
        ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", pady=2)
        e = ttk.Entry(frm, width=width)
        e.insert(0, default)
        e.grid(row=i, column=1, sticky="w", padx=(8, 0), pady=2)
        entries[key] = e

    no_hf_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(frm, text="Wyłącz HF SDR", variable=no_hf_var).grid(
        row=len(fields), column=0, columnspan=2, sticky="w", pady=4)

    # ── Log ──
    log_box = scrolledtext.ScrolledText(root, width=72, height=20,
                                        font=("Courier", 9), state="disabled")
    log_box.grid(row=1, column=0, padx=10, pady=(0, 4))

    def log(msg):
        def _do():
            log_box.configure(state="normal")
            log_box.insert("end", msg + "\n")
            log_box.see("end")
            log_box.configure(state="disabled")
        root.after(0, _do)

    # ── Przyciski ──
    btn_frm = ttk.Frame(root)
    btn_frm.grid(row=2, column=0, pady=(0, 10))

    def start():
        if sim_thread[0] and sim_thread[0].is_alive():
            return
        stop_event.clear()
        try:
            args = {
                "url":       entries["url"].get().strip(),
                "key":       entries["key"].get().strip(),
                "interval":  float(entries["interval"].get()),
                "speed":     float(entries["speed"].get()),
                "apogeum":   float(entries["apogeum"].get()),
                "preflight": int(entries["preflight"].get()),
                "lat":       float(entries["lat"].get()),
                "lon":       float(entries["lon"].get()),
                "no_hf":     no_hf_var.get(),
            }
        except ValueError as e:
            log(f"Błąd parametrów: {e}")
            return
        btn_start.configure(state="disabled")
        btn_stop.configure(state="normal")
        sim_thread[0] = threading.Thread(
            target=_sim_worker, args=(args,), daemon=True)
        sim_thread[0].start()

    def _sim_worker(args):
        run_simulation(args, log, stop_event)
        root.after(0, lambda: (
            btn_start.configure(state="normal"),
            btn_stop.configure(state="disabled"),
        ))

    def stop():
        stop_event.set()
        btn_stop.configure(state="disabled")

    def on_close():
        stop_event.set()
        root.destroy()

    btn_start = ttk.Button(btn_frm, text="▶  Start", command=start, width=14)
    btn_start.grid(row=0, column=0, padx=6)
    btn_stop  = ttk.Button(btn_frm, text="■  Stop",  command=stop,  width=14,
                           state="disabled")
    btn_stop.grid(row=0, column=1, padx=6)

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="StratoSTEAM mission simulator")
    parser.add_argument("--url",       default=_DEFAULT_URL)
    parser.add_argument("--key",       default=_DEFAULT_KEY)
    parser.add_argument("--interval",  type=float, default=5.0)
    parser.add_argument("--speed",     type=float, default=1.0)
    parser.add_argument("--apogeum",   type=float, default=float(APOGEUM_ALT))
    parser.add_argument("--preflight", type=int,   default=3)
    parser.add_argument("--lat",       type=float, default=LAUNCH_LAT)
    parser.add_argument("--lon",       type=float, default=LAUNCH_LON)
    parser.add_argument("--no-hf",     action="store_true")
    parser.add_argument("--cli",       action="store_true",
                        help="Wymuś tryb CLI nawet jeśli wykryto środowisko graficzne")
    args = parser.parse_args()

    if not args.cli and _has_display():
        try:
            run_gui()
            return
        except Exception as e:
            print(f"GUI niedostępne ({e}), przełączam na CLI...")

    # CLI
    stop_event = threading.Event()
    sim_args = {
        "url":       args.url,
        "key":       args.key,
        "interval":  args.interval,
        "speed":     args.speed,
        "apogeum":   args.apogeum,
        "preflight": args.preflight,
        "lat":       args.lat,
        "lon":       args.lon,
        "no_hf":     args.no_hf,
    }
    print(f"\n{BOLD}{'─'*58}")
    print("  StratoSTEAM — Symulator misji balonowej (CLI)")
    print(f"{'─'*58}{RESET}\n")
    try:
        run_simulation(sim_args, print, stop_event)
    except KeyboardInterrupt:
        stop_event.set()
        print(f"\n{YELLOW}Zatrzymano.{RESET}\n")


if __name__ == "__main__":
    main()
