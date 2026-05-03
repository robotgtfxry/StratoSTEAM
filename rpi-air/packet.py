"""
Telemetry packet serialisation (JSON over LoRa).
Keeps it simple — one dict, one json.dumps, one send.
"""
import json
import time
from dataclasses import asdict
from sensors import GpsData, Bme280Data, Ms5611Data, Bno085Data, Ina219Data


def build_packet(
    gps: GpsData,
    bme: Bme280Data,
    ms: Ms5611Data,
    imu: Bno085Data,
    pwr: Ina219Data,
    seq: int,
) -> bytes:
    payload = {
        "seq": seq,
        "ts": int(time.time()),
        "gps": {
            "lat": gps.latitude,
            "lon": gps.longitude,
            "alt": gps.altitude_m,
            "spd": gps.speed_kmh,
            "hdg": gps.heading,
            "sat": gps.satellites,
            "fix": gps.fix,
        },
        "bme": asdict(bme),
        "ms":  asdict(ms),
        "imu": asdict(imu),
        "pwr": asdict(pwr),
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def parse_packet(raw: bytes) -> dict:
    return json.loads(raw.decode())


# ── Uplink (ground → air) ────────────────────────────────────────────────────

def parse_command(raw: bytes) -> dict | None:
    try:
        j = json.loads(raw.decode())
        if "cmd" not in j:
            return None
        return j
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def build_exec_result(rc: int, out: str, err: str) -> bytes:
    # Truncate output to fit LoRa packet (~160 chars each)
    out = out[:160] if len(out) > 160 else out
    err = err[:80]  if len(err) > 80  else err
    return json.dumps(
        {"type": "exec_result", "rc": rc, "out": out, "err": err},
        separators=(",", ":"),
    ).encode()


def build_command(buzzer: bool, r: int, g: int, b: int) -> bytes:
    """Ground station uses this to build the command packet."""
    return json.dumps(
        {"cmd": 1, "buzzer": buzzer, "led_r": r, "led_g": g, "led_b": b},
        separators=(",", ":"),
    ).encode()
