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
