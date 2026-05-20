import time
import RPi.GPIO as GPIO
from dataclasses import dataclass


@dataclass
class Hx711Data:
    strain_g: float = 0.0


class Hx711Sensor:
    """
    HX711 24-bit ADC for strain gauges / load cells.
    Bit-banging via RPi.GPIO — no external library required.
    Tares (zeros) automatically on init.
    reference_unit: raw ADC units per gram (from calibration with known weight).
    """

    def __init__(self, dt_pin: int, sck_pin: int, reference_unit: float = 1.0):
        self._dt  = dt_pin
        self._sck = sck_pin
        self._ref = reference_unit if reference_unit != 0 else 1.0
        self._offset = 0.0

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self._sck, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self._dt, GPIO.IN)

        self._tare()

    # ── low-level ─────────────────────────────────────────────────────────────

    def _ready(self) -> bool:
        return GPIO.input(self._dt) == GPIO.LOW

    def _read_raw(self) -> int:
        deadline = time.monotonic() + 2.0
        while not self._ready():
            if time.monotonic() > deadline:
                raise TimeoutError("HX711 not ready")
            time.sleep(0.001)

        value = 0
        for _ in range(24):
            GPIO.output(self._sck, GPIO.HIGH)
            value = (value << 1) | GPIO.input(self._dt)
            GPIO.output(self._sck, GPIO.LOW)

        # 25th pulse → CH A, gain 128 (next reading)
        GPIO.output(self._sck, GPIO.HIGH)
        GPIO.output(self._sck, GPIO.LOW)

        # 24-bit two's complement → signed int
        if value & 0x800000:
            value -= 0x1000000
        return value

    # ── public ────────────────────────────────────────────────────────────────

    def _tare(self, samples: int = 10):
        readings = []
        for _ in range(samples):
            try:
                readings.append(self._read_raw())
            except TimeoutError:
                pass
        self._offset = sum(readings) / len(readings) if readings else 0.0

    def read(self) -> Hx711Data:
        try:
            raw = self._read_raw()
            grams = (raw - self._offset) / self._ref
            return Hx711Data(strain_g=round(grams, 1))
        except Exception:
            return Hx711Data()

    def close(self):
        GPIO.cleanup([self._dt, self._sck])
