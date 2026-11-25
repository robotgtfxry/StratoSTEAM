"""
Dekodowanie beacona ESP32-S3 i zamiana na format telemetrii backendu.

Beacon musi zmieścić się w 255 B (limit SX1278), więc ESP32 nadaje krótkie klucze
i tablice (esp32/src/main.cpp, sendBeacon):
  p  [lat, lon, alt, sat, fix]        e  [temp, hum, pres, p2, alt2]
  i  [roll, pit, yaw, ax, ay, az]     b  [vbat, imA]
  d  [dsku, dskf]   h  hfdb   c  [ok, rec, klatki, wolne_MB]
  g  [widoczne satelity, max SNR, zdania ok, zdania złe]
  x  1 = część pól pominięta, bo pakiet byłby za długi

Stary, płaski format (lat, temp, vbat, …) jest nadal rozumiany.
"""
import time

_GROUPS = {
    "p": ("lat", "lon", "alt", "sat", "fix"),
    "e": ("temp", "hum", "pres", "p2", "alt2"),
    "i": ("roll", "pit", "yaw", "ax", "ay", "az"),
    "b": ("vbat", "imA"),
    "d": ("dsku", "dskf"),
    "g": ("gview", "gsnr", "gok", "gbad"),
}


def expand_beacon(packet: dict) -> dict:
    """Krótkie klucze → płaski słownik z pełnymi nazwami. Starego formatu nie zmienia."""
    flat = dict(packet)
    for key, names in _GROUPS.items():
        values = flat.pop(key, None)
        if isinstance(values, list):
            flat.update(zip(names, values))
    if "h" in flat:
        flat["hfdb"] = flat.pop("h")
    if "c" in flat:
        flat["ec"] = flat.pop("c")
    return flat


def has_rpi_data(flat: dict) -> bool:
    """Czy beacon niesie świeże dane z RPi5 (czyli RPi na balonie działa)."""
    return "temp" in flat


def beacon_to_telemetry(flat: dict, now: float | None = None) -> dict:
    """Rozwinięty beacon → struktura TelemetryIn backendu."""
    def num(key: str) -> float:
        return float(flat.get(key) or 0.0)

    fix = bool(flat.get("fix"))
    volt = num("vbat") or num("vbe")      # INA219, a gdy brak — pomiar ESP32
    return {
        "seq": int(flat.get("seq") or 0),
        "ts": int(time.time() if now is None else now),   # beacon nie ma zegara
        "gps": {
            # bez fixa ESP32 wysyła zera — nie rysuj balonu na 0°N 0°E
            "lat": num("lat") if fix else None,
            "lon": num("lon") if fix else None,
            "alt": num("alt") if fix else None,
            "sat": int(num("sat")),
            "fix": fix,
        },
        "bme": {"temperature_c": num("temp"), "humidity_pct": num("hum"),
                "pressure_hpa": num("pres")},
        "ms":  {"pressure_hpa": num("p2"), "altitude_m": num("alt2")},
        "imu": {"roll_deg": num("roll"), "pitch_deg": num("pit"), "yaw_deg": num("yaw"),
                "accel_x": num("ax"), "accel_y": num("ay"), "accel_z": num("az")},
        "pwr": {"voltage_v": volt, "current_ma": num("imA"),
                "power_mw": round(volt * num("imA"), 2)},
    }
