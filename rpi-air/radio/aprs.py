"""
APRS beacon via AD9833 + LPF-B0R35+ + RD06HHF1 on 144.800 MHz.
AD9833 generates AFSK audio tones (1200/2200 Hz) fed into the TX chain.
"""
import spidev
import RPi.GPIO as GPIO
import time
from config import AD9833_SPI_BUS, AD9833_SPI_CS, APRS_CALLSIGN

_AD9833_MCLK = 25_000_000   # 25 MHz crystal on module
_FREQ0 = 0x4000
_FREQ1 = 0x8000
_CTRL_B28 = 0x2000
_CTRL_RESET = 0x0100

_MARK_HZ = 1200
_SPACE_HZ = 2200


def _freq_word(hz: int) -> int:
    return round(hz * (1 << 28) / _AD9833_MCLK)


class Ad9833Aprs:
    """Bit-bang AFSK 1200 baud AX.25 / APRS over AD9833."""

    def __init__(self, ptt_pin: int = 24):
        self._ptt = ptt_pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(ptt_pin, GPIO.OUT, initial=GPIO.LOW)
        self._spi = spidev.SpiDev()
        self._spi.open(AD9833_SPI_BUS, AD9833_SPI_CS)
        self._spi.max_speed_hz = 1_000_000
        self._spi.mode = 0b10   # SPI mode 2
        self._init_chip()

    def _write(self, word: int):
        self._spi.xfer2([(word >> 8) & 0xFF, word & 0xFF])

    def _init_chip(self):
        self._write(_CTRL_B28 | _CTRL_RESET)
        fw = _freq_word(_MARK_HZ)
        self._write(_FREQ0 | (fw & 0x3FFF))
        self._write(_FREQ0 | ((fw >> 14) & 0x3FFF))
        self._write(0xC000)   # phase 0
        self._write(_CTRL_B28)   # release reset, sinusoid output

    def _set_freq(self, hz: int):
        fw = _freq_word(hz)
        self._write(_CTRL_B28)
        self._write(_FREQ0 | (fw & 0x3FFF))
        self._write(_FREQ0 | ((fw >> 14) & 0x3FFF))

    def _send_bit(self, bit: int, t: float = 1 / 1200):
        self._set_freq(_MARK_HZ if bit else _SPACE_HZ)
        time.sleep(t)

    def _nrzi_encode(self, bits: list[int]) -> list[int]:
        out, last = [], 1
        for b in bits:
            if b == 0:
                last ^= 1
            out.append(last)
        return out

    def _build_ax25(self, lat: float, lon: float, alt_m: float) -> bytes:
        """Minimal AX.25 UI frame with APRS position."""
        lat_d = abs(lat)
        lon_d = abs(lon)
        lat_str = f"{int(lat_d):02d}{(lat_d % 1) * 60:05.2f}{'N' if lat >= 0 else 'S'}"
        lon_str = f"{int(lon_d):03d}{(lon_d % 1) * 60:05.2f}{'E' if lon >= 0 else 'W'}"
        alt_ft = int(alt_m * 3.28084)
        info = f"!{lat_str}/{lon_str}O/A={alt_ft:06d} StratoSTEAM".encode()

        dest = b"APRS  \xe0"
        src = (APRS_CALLSIGN.ljust(6).encode() + b"\x00")[:7]
        path = b"WIDE2 \xe1"
        header = dest + src + path + b"\x03\xf0"
        frame = header + info

        # FCS (CRC-CCITT)
        crc = 0xFFFF
        for byte in frame:
            for _ in range(8):
                bit = (byte ^ (crc & 0xFF)) & 0x01
                crc >>= 1
                if bit:
                    crc ^= 0x8408
                byte >>= 1
        fcs = bytes([crc & 0xFF, (crc >> 8) & 0xFF])
        return frame + fcs

    def beacon(self, lat: float, lon: float, alt_m: float):
        frame = self._build_ax25(lat, lon, alt_m)
        # convert to bits with bit-stuffing
        bits = [1] * 8 + self._ax25_bits(frame) + [1] * 8
        nrzi = self._nrzi_encode(bits)
        GPIO.output(self._ptt, GPIO.HIGH)
        time.sleep(0.3)   # TX up time
        for b in nrzi:
            self._send_bit(b)
        GPIO.output(self._ptt, GPIO.LOW)

    def _ax25_bits(self, data: bytes) -> list[int]:
        bits, ones = [], 0
        for byte in data:
            for i in range(8):
                b = (byte >> i) & 1
                bits.append(b)
                if b:
                    ones += 1
                    if ones == 5:
                        bits.append(0)
                        ones = 0
                else:
                    ones = 0
        return bits

    def close(self):
        GPIO.cleanup()
        self._spi.close()
