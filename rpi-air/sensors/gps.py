import serial
import pynmea2
import logging
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class GpsData:
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_m: Optional[float] = None
    speed_kmh: Optional[float] = None
    heading: Optional[float] = None
    satellites: int = 0
    fix: bool = False


class NeoM8nGps:
    def __init__(self, port: str, baud: int = 9600):
        self._ser = serial.Serial(port, baud, timeout=1)
        self._data = GpsData()

    def update(self) -> bool:
        """Read one NMEA sentence. Returns True when position updated."""
        try:
            raw = self._ser.readline().decode("ascii", errors="replace").strip()
            if not raw.startswith("$"):
                return False
            msg = pynmea2.parse(raw)
            if isinstance(msg, pynmea2.GGA):
                self._data.fix = msg.gps_qual > 0
                self._data.satellites = int(msg.num_sats or 0)
                if self._data.fix:
                    self._data.latitude = msg.latitude
                    self._data.longitude = msg.longitude
                    self._data.altitude_m = float(msg.altitude or 0)
                return True
            if isinstance(msg, pynmea2.RMC) and msg.status == "A":
                self._data.speed_kmh = float(msg.spd_over_grnd or 0) * 1.852
                self._data.heading = float(msg.true_course or 0)
        except (pynmea2.ParseError, ValueError, serial.SerialException) as e:
            log.debug("GPS parse error: %s", e)
        return False

    @property
    def data(self) -> GpsData:
        return self._data

    def close(self):
        self._ser.close()
