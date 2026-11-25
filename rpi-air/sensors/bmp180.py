"""
BMP180 (płytka GY-87): ciśnienie i wysokość barometryczna.
UWAGA: zakres kończy się na 300 hPa (~9 km). Wyżej wysokość bierz z GPS.
"""
import time

import smbus2

from .ms5611 import Ms5611Data

_OSS = 3


def _tdiv(a: int, b: int) -> int:
    """Dzielenie całkowite z obcięciem do zera — jak w C (algorytm z noty)."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def compensate(cal: list[int], ut: int, up: int, oss: int = _OSS) -> tuple[float, float]:
    """(temperatura °C, ciśnienie hPa) — algorytm z noty katalogowej Boscha."""
    ac1, ac2, ac3, ac4, ac5, ac6, b1, b2, _mb, mc, md = cal
    x1 = ((ut - ac6) * ac5) >> 15
    x2 = _tdiv(mc << 11, x1 + md)
    b5 = x1 + x2
    temp_c = ((b5 + 8) >> 4) / 10.0

    b6 = b5 - 4000
    x1 = (b2 * ((b6 * b6) >> 12)) >> 11
    x2 = (ac2 * b6) >> 11
    b3 = _tdiv(((ac1 * 4 + x1 + x2) << oss) + 2, 4)
    x1 = (ac3 * b6) >> 13
    x2 = (b1 * ((b6 * b6) >> 12)) >> 16
    b4 = (ac4 * (((x1 + x2 + 2) >> 2) + 32768)) >> 15
    b7 = (up - b3) * (50000 >> oss)
    p = _tdiv(b7 * 2, b4) if b7 < 0x80000000 else _tdiv(b7, b4) * 2
    x1 = ((p >> 8) * (p >> 8) * 3038) >> 16
    x2 = (-7357 * p) >> 16
    p += (x1 + x2 + 3791) >> 4
    return temp_c, p / 100.0


class Bmp180Sensor:
    def __init__(self, i2c_addr: int = 0x77, bus: int = 1):
        self._bus = smbus2.SMBus(bus)
        self._addr = i2c_addr
        cid = self._bus.read_byte_data(i2c_addr, 0xD0)
        if cid != 0x55:     # MS5611 i BME280 mogą mieć ten sam adres
            raise OSError(f"pod 0x{i2c_addr:02X} nie ma BMP180 (chip ID 0x{cid:02X})")
        c = self._bus.read_i2c_block_data(i2c_addr, 0xAA, 22)
        # AC4, AC5, AC6 (indeksy 3–5) są bez znaku, reszta ze znakiem
        self._cal = [int.from_bytes(bytes(c[2 * i:2 * i + 2]), "big", signed=i not in (3, 4, 5))
                     for i in range(11)]
        if 0 in self._cal[3:6] or self._cal[10] == 0:
            raise OSError("nieprawidłowe dane kalibracyjne BMP180")

    def read(self) -> Ms5611Data:
        try:
            self._bus.write_byte_data(self._addr, 0xF4, 0x2E)
            time.sleep(0.005)
            b = self._bus.read_i2c_block_data(self._addr, 0xF6, 2)
            ut = (b[0] << 8) | b[1]
            self._bus.write_byte_data(self._addr, 0xF4, 0x34 + (_OSS << 6))
            time.sleep(0.026)
            b = self._bus.read_i2c_block_data(self._addr, 0xF6, 3)
            up = ((b[0] << 16) | (b[1] << 8) | b[2]) >> (8 - _OSS)
            temp, pressure = compensate(self._cal, ut, up)
        except (OSError, ZeroDivisionError):
            return Ms5611Data()
        if pressure <= 0:
            return Ms5611Data()
        return Ms5611Data(
            temperature_c=round(temp, 2),
            pressure_hpa=round(pressure, 2),
            altitude_m=round(44330.0 * (1.0 - (pressure / 1013.25) ** 0.1903), 1),
        )
