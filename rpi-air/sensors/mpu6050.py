"""
MPU-6050 (płytka GY-87): przyspieszenie oraz roll/pitch liczone z grawitacji.
Yaw = 0: układ nie ma magnetometru, a kompas z GY-87 wymaga osobnej kalibracji.
"""
import math

import smbus2

from .bno085 import Bno085Data

_G = 9.80665
_LSB_PER_G = 4096.0      # zakres ±8 g — zapas na szarpnięcie przy pęknięciu balonu


class Mpu6050Sensor:
    def __init__(self, i2c_addr: int = 0x68, bus: int = 1):
        self._bus = smbus2.SMBus(bus)
        self._addr = i2c_addr
        self._configure()

    def _configure(self) -> None:
        who = self._bus.read_byte_data(self._addr, 0x75)
        if who not in (0x68, 0x70, 0x71, 0x72, 0x73, 0x98):
            raise OSError(f"pod 0x{self._addr:02X} nie ma MPU-6050 (WHO_AM_I=0x{who:02X})")
        self._bus.write_byte_data(self._addr, 0x6B, 0x01)   # wybudź, zegar z PLL
        self._bus.write_byte_data(self._addr, 0x1A, 0x03)   # filtr DLPF ~44 Hz
        self._bus.write_byte_data(self._addr, 0x1C, 0x10)   # akcelerometr ±8 g
        self._ready = True

    def read(self) -> Bno085Data:
        try:
            if not self._ready:
                self._configure()       # po zaniku zasilania układ wraca do uśpienia
            b = self._bus.read_i2c_block_data(self._addr, 0x3B, 6)
        except OSError:
            self._ready = False
            return Bno085Data()
        raw = [int.from_bytes(bytes(b[i:i + 2]), "big", signed=True) for i in (0, 2, 4)]
        if not any(raw):                # same zera = uśpiony po chwilowym zaniku zasilania
            self._ready = False
            return Bno085Data()
        ax, ay, az = (v / _LSB_PER_G * _G for v in raw)
        return Bno085Data(
            roll_deg=round(math.degrees(math.atan2(ay, az)), 2),
            pitch_deg=round(math.degrees(math.atan2(-ax, math.hypot(ay, az))), 2),
            yaw_deg=0.0,
            accel_x=round(ax, 3),
            accel_y=round(ay, 3),
            accel_z=round(az, 3),
        )
