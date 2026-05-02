import smbus2
import time
from dataclasses import dataclass


@dataclass
class Ms5611Data:
    temperature_c: float = 0.0
    pressure_hpa: float = 0.0
    altitude_m: float = 0.0   # derived from pressure


# MS5611 register commands
_CMD_RESET = 0x1E
_CMD_PROM_READ = 0xA0
_CMD_CONVERT_D1 = 0x48   # pressure OSR=4096
_CMD_CONVERT_D2 = 0x58   # temperature OSR=4096
_CMD_ADC_READ = 0x00


class Ms5611Sensor:
    def __init__(self, i2c_addr: int = 0x77, bus: int = 1):
        self._bus = smbus2.SMBus(bus)
        self._addr = i2c_addr
        self._cal = self._read_calibration()

    def _read_calibration(self) -> list[int]:
        self._bus.write_byte(self._addr, _CMD_RESET)
        time.sleep(0.01)
        cal = []
        for i in range(6):
            data = self._bus.read_i2c_block_data(self._addr, _CMD_PROM_READ + i * 2, 2)
            cal.append((data[0] << 8) | data[1])
        return cal

    def _read_raw(self, cmd: int) -> int:
        self._bus.write_byte(self._addr, cmd)
        time.sleep(0.01)
        data = self._bus.read_i2c_block_data(self._addr, _CMD_ADC_READ, 3)
        return (data[0] << 16) | (data[1] << 8) | data[2]

    def read(self) -> Ms5611Data:
        c1, c2, c3, c4, c5, c6 = self._cal
        d1 = self._read_raw(_CMD_CONVERT_D1)
        d2 = self._read_raw(_CMD_CONVERT_D2)

        dt = d2 - c5 * 256
        temp = (2000 + dt * c6 // 8388608) / 100.0

        off = c2 * 65536 + (c4 * dt) // 128
        sens = c1 * 32768 + (c3 * dt) // 256
        pressure = ((d1 * sens // 2097152 - off) // 32768) / 100.0

        # barometric altitude (ISA model, good enough for stratosphere)
        altitude = 44330.0 * (1.0 - (pressure / 1013.25) ** 0.1903)

        return Ms5611Data(
            temperature_c=round(temp, 2),
            pressure_hpa=round(pressure, 2),
            altitude_m=round(altitude, 1),
        )
