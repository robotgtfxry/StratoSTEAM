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


def build_photo_command() -> bytes:
    return json.dumps({"cmd": "photo"}, separators=(",", ":")).encode()


def build_cam_rec_command(on: bool) -> bytes:
    return json.dumps({"cmd": "cam_rec", "on": on}, separators=(",", ":")).encode()
