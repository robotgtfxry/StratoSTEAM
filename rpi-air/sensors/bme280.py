import smbus2
from bme280 import BME280 as _BME280
from dataclasses import dataclass


@dataclass
class Bme280Data:
    temperature_c: float = 0.0
    humidity_pct: float = 0.0
    pressure_hpa: float = 0.0


class Bme280Sensor:
    def __init__(self, i2c_addr: int = 0x76, bus: int = 1):
        self._bus = smbus2.SMBus(bus)
        self._sensor = _BME280(i2c_addr=i2c_addr, i2c_dev=self._bus)

    def read(self) -> Bme280Data:
        return Bme280Data(
            temperature_c=round(self._sensor.get_temperature(), 2),
            humidity_pct=round(self._sensor.get_humidity(), 2),
            pressure_hpa=round(self._sensor.get_pressure(), 2),
        )
