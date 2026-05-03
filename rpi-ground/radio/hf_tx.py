"""
HF transmitter: AD9833 (waveform) → LPF-B0R35+ (filter) → RD06HHF1 (PA).
Used for ionospheric reflection testing on rpi-ground.
"""
import spidev
import RPi.GPIO as GPIO
import threading
import logging
from config import AD9833_SPI_BUS, AD9833_SPI_CS, AD9833_MCLK_HZ, HF_PTT_PIN

log = logging.getLogger(__name__)

# AD9833 control register bits
_CTRL_B28   = 1 << 13
_CTRL_RESET = 1 << 8
_CTRL_SINE  = 0x0000   # sinusoid output (default after reset)
_FREQ0_REG  = 0x4000
_PHASE0_REG = 0xC000


def _freq_words(hz: int) -> tuple[int, int]:
    """Split frequency into two 14-bit words for B28 mode."""
    word = round(hz * (1 << 28) / AD9833_MCLK_HZ) & 0x0FFFFFFF
    return (word & 0x3FFF), ((word >> 14) & 0x3FFF)


class HfTransmitter:
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(HF_PTT_PIN, GPIO.OUT, initial=GPIO.LOW)

        self._spi = spidev.SpiDev()
        self._spi.open(AD9833_SPI_BUS, AD9833_SPI_CS)
        self._spi.max_speed_hz = 1_000_000
        self._spi.mode = 0b10   # SPI mode 2 (CPOL=1, CPHA=0)

        self._lock = threading.Lock()
        self._active = False
        self._freq_hz = 0

        self._init_chip()
        log.info("HF transmitter ready (AD9833)")

    def _write(self, word: int):
        self._spi.xfer2([(word >> 8) & 0xFF, word & 0xFF])

    def _init_chip(self):
        self._write(_CTRL_B28 | _CTRL_RESET)   # reset, B28 mode
        lo, hi = _freq_words(0)
        self._write(_FREQ0_REG | lo)
        self._write(_FREQ0_REG | hi)
        self._write(_PHASE0_REG)                # phase = 0
        self._write(_CTRL_B28)                  # release reset, sine out

    def start(self, freq_hz: int):
        with self._lock:
            if self._active and self._freq_hz == freq_hz:
                return
            self._set_freq(freq_hz)
            GPIO.output(HF_PTT_PIN, GPIO.HIGH)   # key the PA
            self._active = True
            self._freq_hz = freq_hz
            log.info("HF TX ON  %.6f MHz", freq_hz / 1e6)

    def stop(self):
        with self._lock:
            if not self._active:
                return
            GPIO.output(HF_PTT_PIN, GPIO.LOW)    # unkey PA first
            self._write(_CTRL_B28 | _CTRL_RESET) # mute AD9833
            self._active = False
            self._freq_hz = 0
            log.info("HF TX OFF")

    def set_freq(self, freq_hz: int):
        with self._lock:
            if self._active:
                self._set_freq(freq_hz)
                self._freq_hz = freq_hz
                log.info("HF freq changed → %.6f MHz", freq_hz / 1e6)

    def _set_freq(self, freq_hz: int):
        lo, hi = _freq_words(freq_hz)
        self._write(_CTRL_B28)
        self._write(_FREQ0_REG | lo)
        self._write(_FREQ0_REG | hi)

    @property
    def status(self) -> dict:
        return {"active": self._active, "freq_hz": self._freq_hz}

    def close(self):
        self.stop()
        self._spi.close()
        GPIO.cleanup()
