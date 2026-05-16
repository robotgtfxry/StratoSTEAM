"""
AD9833 — czysta nośna sinusoidalna na 144.800 MHz.
Brak modulacji.
Używana jako sygnał referencyjny do testu odbicia jonosferycznego
(SDR na ziemi wykrywa czy sygnał z balonu wraca po odbiciu).
"""
import spidev
import RPi.GPIO as GPIO
from config import AD9833_SPI_BUS, AD9833_SPI_CS, AD9833_CARRIER_FREQ

_MCLK       = 25_000_000
_CTRL_B28   = 0x2000
_CTRL_RESET = 0x0100
_FREQ0      = 0x4000
_PHASE0     = 0xC000


class CarrierBeacon:
    """Nośna 144.800 MHz generowana przez AD9833 na RPi-air."""
    def __init__(self, ptt_pin: int = 24):
        self._ptt = ptt_pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(ptt_pin, GPIO.OUT, initial=GPIO.LOW)

        self._spi = spidev.SpiDev()
        self._spi.open(AD9833_SPI_BUS, AD9833_SPI_CS)
        self._spi.max_speed_hz = 1_000_000
        self._spi.mode = 0b10   # SPI mode 2

        self._program_freq()

    def _write(self, word: int):
        self._spi.xfer2([(word >> 8) & 0xFF, word & 0xFF])

    def _program_freq(self):
        fw = round(AD9833_CARRIER_FREQ * (1 << 28) / _MCLK) & 0x0FFFFFFF
        self._write(_CTRL_B28 | _CTRL_RESET)
        self._write(_FREQ0 | (fw & 0x3FFF))
        self._write(_FREQ0 | ((fw >> 14) & 0x3FFF))
        self._write(_PHASE0)
        self._write(_CTRL_B28)   # release reset → sine output on VOUT

    def start(self):
        GPIO.output(self._ptt, GPIO.HIGH)

    def stop(self):
        GPIO.output(self._ptt, GPIO.LOW)

    def close(self):
        self.stop()
        self._spi.close()
        GPIO.cleanup(self._ptt)
