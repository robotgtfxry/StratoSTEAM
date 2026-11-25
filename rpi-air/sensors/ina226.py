"""INA226 — napięcie i prąd baterii (I2C)."""
import smbus2

from .ina219 import Ina219Data


class Ina226Sensor:
    def __init__(self, shunt_ohms: float = 0.1, i2c_addr: int = 0x44, bus: int = 1):
        self._bus = smbus2.SMBus(bus)
        self._addr = i2c_addr
        self._shunt = shunt_ohms
        if self._reg(0xFE) != 0x5449:
            raise OSError(f"pod 0x{i2c_addr:02X} nie ma INA226")
        self._configure()

    def _configure(self) -> None:
        # uśrednianie 16, konwersja 1.1 ms, pomiar ciągły bocznika i szyny
        self._bus.write_i2c_block_data(self._addr, 0x00, [0x45, 0x27])

    def _reg(self, reg: int, signed: bool = False) -> int:
        return int.from_bytes(bytes(self._bus.read_i2c_block_data(self._addr, reg, 2)),
                              "big", signed=signed)

    def read(self) -> Ina219Data:
        try:
            voltage = self._reg(0x02) * 0.00125                              # 1.25 mV/LSB
            current = self._reg(0x01, signed=True) * 0.0025 / self._shunt    # 2.5 µV/LSB → mA
        except OSError:
            return Ina219Data()
        return Ina219Data(
            voltage_v=round(voltage, 3),
            current_ma=round(current, 2),
            power_mw=round(voltage * current, 2),
        )
