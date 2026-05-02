from ina219 import INA219 as _INA219
from ina219 import DeviceRangeError
from dataclasses import dataclass


@dataclass
class Ina219Data:
    voltage_v: float = 0.0
    current_ma: float = 0.0
    power_mw: float = 0.0


class Ina219Sensor:
    def __init__(self, shunt_ohms: float = 0.1, i2c_addr: int = 0x40):
        self._ina = _INA219(shunt_ohms, address=i2c_addr)
        self._ina.configure()

    def read(self) -> Ina219Data:
        try:
            return Ina219Data(
                voltage_v=round(self._ina.voltage(), 3),
                current_ma=round(self._ina.current(), 2),
                power_mw=round(self._ina.power(), 2),
            )
        except DeviceRangeError:
            return Ina219Data()
