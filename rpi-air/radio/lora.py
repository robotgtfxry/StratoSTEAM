import spidev
import RPi.GPIO as GPIO
import time
import struct
import logging
from config import (
    LORA_FREQ, LORA_SF, LORA_BW, LORA_CR,
    LORA_TX_POWER, LORA_SPI_BUS, LORA_SPI_CS, LORA_DIO0_PIN,
)

log = logging.getLogger(__name__)

# SX1278 registers
_REG_FIFO = 0x00
_REG_OP_MODE = 0x01
_REG_FRF_MSB = 0x06
_REG_FRF_MID = 0x07
_REG_FRF_LSB = 0x08
_REG_PA_CONFIG = 0x09
_REG_FIFO_ADDR_PTR = 0x0D
_REG_FIFO_TX_BASE_ADDR = 0x0E
_REG_FIFO_RX_BASE_ADDR = 0x0F
_REG_FIFO_RX_CURRENT_ADDR = 0x10
_REG_IRQ_FLAGS = 0x12
_REG_RX_NB_BYTES = 0x13
_REG_PKT_SNR_VALUE = 0x19
_REG_PKT_RSSI_VALUE = 0x1A
_REG_MODEM_CONFIG1 = 0x1D
_REG_MODEM_CONFIG2 = 0x1E
_REG_PAYLOAD_LENGTH = 0x22
_REG_MODEM_CONFIG3 = 0x26
_REG_SYNC_WORD = 0x39
_REG_DIO_MAPPING1 = 0x40
_REG_VERSION = 0x42

_MODE_SLEEP = 0x00
_MODE_STDBY = 0x01
_MODE_TX = 0x03
_MODE_RX_CONT = 0x05
_MODE_LONG_RANGE = 0x80

_IRQ_TX_DONE = 0x08
_IRQ_RX_DONE = 0x40


class LoRaSX1278:
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(LORA_DIO0_PIN, GPIO.IN)

        self._spi = spidev.SpiDev()
        self._spi.open(LORA_SPI_BUS, LORA_SPI_CS)
        self._spi.max_speed_hz = 5000000

        self._reset()
        assert self._read_reg(_REG_VERSION) == 0x12, "SX1278 not found on SPI"
        self._configure()
        log.info("LoRa SX1278 ready, freq=%.1f MHz SF=%d", LORA_FREQ, LORA_SF)

    def _reset(self):
        self._write_reg(_REG_OP_MODE, _MODE_SLEEP)
        time.sleep(0.01)

    def _configure(self):
        self._write_reg(_REG_OP_MODE, _MODE_LONG_RANGE | _MODE_SLEEP)
        # frequency
        frf = int((LORA_FREQ * 1e6) / 61.03515625)
        self._write_reg(_REG_FRF_MSB, (frf >> 16) & 0xFF)
        self._write_reg(_REG_FRF_MID, (frf >> 8) & 0xFF)
        self._write_reg(_REG_FRF_LSB, frf & 0xFF)
        # TX power (PA_BOOST pin)
        self._write_reg(_REG_PA_CONFIG, 0x80 | (LORA_TX_POWER - 2))
        # modem config
        bw_map = {7800: 0, 10400: 1, 15600: 2, 20800: 3, 31250: 4,
                  41700: 5, 62500: 6, 125000: 7, 250000: 8, 500000: 9}
        bw_bits = bw_map.get(LORA_BW, 7) << 4
        cr_bits = (LORA_CR - 4) << 1
        self._write_reg(_REG_MODEM_CONFIG1, bw_bits | cr_bits)
        self._write_reg(_REG_MODEM_CONFIG2, (LORA_SF << 4) | 0x04)
        self._write_reg(_REG_MODEM_CONFIG3, 0x04)   # LNA gain auto
        self._write_reg(_REG_SYNC_WORD, 0x12)        # private network
        self._write_reg(_REG_FIFO_TX_BASE_ADDR, 0x00)
        self._write_reg(_REG_FIFO_RX_BASE_ADDR, 0x00)
        self._set_mode(_MODE_STDBY)

    def send(self, data: bytes) -> bool:
        self._set_mode(_MODE_STDBY)
        self._write_reg(_REG_FIFO_ADDR_PTR, 0x00)
        for b in data:
            self._write_reg(_REG_FIFO, b)
        self._write_reg(_REG_PAYLOAD_LENGTH, len(data))
        self._write_reg(_REG_DIO_MAPPING1, 0x40)  # DIO0 = TxDone
        self._set_mode(_MODE_TX)
        # wait for TxDone (max 5 s)
        deadline = time.time() + 5
        while time.time() < deadline:
            if self._read_reg(_REG_IRQ_FLAGS) & _IRQ_TX_DONE:
                self._write_reg(_REG_IRQ_FLAGS, _IRQ_TX_DONE)
                self._set_mode(_MODE_STDBY)
                return True
            time.sleep(0.01)
        log.warning("LoRa TX timeout")
        return False

    def _set_mode(self, mode: int):
        self._write_reg(_REG_OP_MODE, _MODE_LONG_RANGE | mode)

    def _write_reg(self, reg: int, val: int):
        self._spi.xfer2([reg | 0x80, val])

    def _read_reg(self, reg: int) -> int:
        return self._spi.xfer2([reg & 0x7F, 0])[1]

    def close(self):
        self._spi.close()
        GPIO.cleanup()
