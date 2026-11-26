"""Uplink packet builders for ground station."""
import json


def build_command(buzzer: bool, r: int, g: int, b: int) -> bytes:
    return json.dumps(
        {"cmd": 1, "buzzer": buzzer, "led_r": r, "led_g": g, "led_b": b},
        separators=(",", ":"),
    ).encode()


def build_rpi_power_command(on: bool) -> bytes:
    return json.dumps(
        {"cmd": "rpi_power", "on": on},
        separators=(",", ":"),
    ).encode()


def build_exec_command(sh: str) -> bytes:
    # Truncate to leave room for LoRa overhead (~255 byte limit)
    if len(sh) > 180:
        sh = sh[:180]
    return json.dumps(
        {"cmd": "exec", "sh": sh},
        separators=(",", ":"),
    ).encode()


def build_photo_command(sf: int = 10) -> bytes:
    return json.dumps({"cmd": "photo", "sf": sf}, separators=(",", ":")).encode()


def build_buzzer_command(on: bool, ms: int = 0) -> bytes:
    """Buzzer na ESP32-S3 (GPIO2). ms > 0 — sam się wyłączy; 0 — gra do komendy wyłączenia."""
    cmd = {"cmd": 1, "buzzer": on}
    if on and ms > 0:
        cmd["ms"] = ms
    return json.dumps(cmd, separators=(",", ":")).encode()


def build_callsign_command(cs: str) -> bytes:
    """Nowy znak wywoławczy sondy (S3 zapamiętuje go na stałe)."""
    return json.dumps({"cmd": "cs", "v": cs}, separators=(",", ":")).encode()


def build_flight_command(on: bool) -> bytes:
    return json.dumps({"cmd": "flight", "on": on}, separators=(",", ":")).encode()


def build_raw_command(cmd: dict) -> bytes:
    return json.dumps(cmd, separators=(",", ":")).encode()


def build_cam_rec_command(on: bool) -> bytes:
    return json.dumps({"cmd": "cam_rec", "on": on}, separators=(",", ":")).encode()


def build_espcam_power_command(on: bool) -> bytes:
    """Zasilanie jedynej kamery ESP32-CAM na balonie."""
    return json.dumps({"cmd": "espcam_pwr", "on": on}, separators=(",", ":")).encode()
