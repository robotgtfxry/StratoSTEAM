import spidev
import RPi.GPIO as GPIO
import time
import logging
from config import (
    LORA_FREQ, LORA_SF, LORA_BW, LORA_CR,
    LORA_SPI_BUS, LORA_SPI_CS, LORA_DIO0_PIN,
)

log = logging.getLogger(__name__)

# SX1278 registers (same as air side)
_REG_FIFO = 0x00
_REG_OP_MODE = 0x01
_REG_FRF_MSB = 0x06
_REG_FRF_MID = 0x07
_REG_FRF_LSB = 0x08
_REG_MODEM_CONFIG1 = 0x1D
_REG_MODEM_CONFIG2 = 0x1E
_REG_MODEM_CONFIG3 = 0x26
_REG_FIFO_ADDR_PTR = 0x0D
_REG_FIFO_RX_BASE_ADDR = 0x0F
_REG_FIFO_RX_CURRENT_ADDR = 0x10
_REG_IRQ_FLAGS = 0x12
_REG_RX_NB_BYTES = 0x13
_REG_PKT_SNR_VALUE = 0x19
_REG_PKT_RSSI_VALUE = 0x1A
_REG_SYNC_WORD = 0x39
_REG_DIO_MAPPING1 = 0x40
_REG_VERSION = 0x42

_MODE_SLEEP = 0x00
_MODE_STDBY = 0x01
_MODE_RX_CONT = 0x05
_MODE_LONG_RANGE = 0x80
_IRQ_RX_DONE = 0x40
_IRQ_PAYLOAD_CRC_ERROR = 0x20


class LoRaRX:
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(LORA_DIO0_PIN, GPIO.IN)
        self._spi = spidev.SpiDev()
        self._spi.open(LORA_SPI_BUS, LORA_SPI_CS)
        self._spi.max_speed_hz = 5_000_000
        assert self._read_reg(_REG_VERSION) == 0x12, "SX1278 not found"
        self._configure()
        log.info("LoRa RX ready")

    def _configure(self):
        self._write_reg(_REG_OP_MODE, _MODE_LONG_RANGE | _MODE_SLEEP)
        frf = int((LORA_FREQ * 1e6) / 61.03515625)
        self._write_reg(_REG_FRF_MSB, (frf >> 16) & 0xFF)
        self._write_reg(_REG_FRF_MID, (frf >> 8) & 0xFF)
        self._write_reg(_REG_FRF_LSB, frf & 0xFF)
        bw_map = {125000: 7, 250000: 8, 500000: 9}
        bw_bits = bw_map.get(LORA_BW, 7) << 4
        cr_bits = (LORA_CR - 4) << 1
        self._write_reg(_REG_MODEM_CONFIG1, bw_bits | cr_bits | 0x01)  # implicit CRC
        self._write_reg(_REG_MODEM_CONFIG2, (LORA_SF << 4) | 0x04)
        self._write_reg(_REG_MODEM_CONFIG3, 0x04)
        self._write_reg(_REG_SYNC_WORD, 0x12)
        self._write_reg(_REG_FIFO_RX_BASE_ADDR, 0x00)
        self._write_reg(_REG_DIO_MAPPING1, 0x00)  # DIO0 = RxDone
        self._set_mode(_MODE_RX_CONT)

    def receive(self, timeout_s: float = 1.0) -> tuple[bytes | None, int, float]:
        """
        Returns (payload_bytes, rssi_dbm, snr_db) or (None, 0, 0) on timeout.
        """
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            irq = self._read_reg(_REG_IRQ_FLAGS)
            if irq & _IRQ_RX_DONE:
                if irq & _IRQ_PAYLOAD_CRC_ERROR:
                    self._write_reg(_REG_IRQ_FLAGS, 0xFF)
                    log.warning("CRC error")
                    return None, 0, 0
                length = self._read_reg(_REG_RX_NB_BYTES)
                self._write_reg(_REG_FIFO_ADDR_PTR, self._read_reg(_REG_FIFO_RX_CURRENT_ADDR))
                payload = bytes([self._read_reg(_REG_FIFO) for _ in range(length)])
                snr = (self._read_reg(_REG_PKT_SNR_VALUE) / 4.0)
                rssi = self._read_reg(_REG_PKT_RSSI_VALUE) - 157
                self._write_reg(_REG_IRQ_FLAGS, 0xFF)
                return payload, rssi, snr
            time.sleep(0.005)
        return None, 0, 0

    def send_command(self, data: bytes) -> bool:
        """
        Switch briefly to TX, send command packet, return to RX_CONT.
        Called immediately after receiving a telemetry packet — the balloon
        is listening for exactly UPLINK_RX_WINDOW_S seconds.
        """
        self._set_mode(_MODE_STDBY)
        self._write_reg(_REG_FIFO_ADDR_PTR, 0x00)
        self._write_reg(0x0E, 0x00)   # FIFO TX base
        for b in data:
            self._write_reg(_REG_FIFO, b)
        self._write_reg(0x22, len(data))   # payload length
        self._write_reg(_REG_DIO_MAPPING1, 0x40)
        self._set_mode(0x03)   # TX mode
        deadline = time.time() + 5
        while time.time() < deadline:
            if self._read_reg(_REG_IRQ_FLAGS) & 0x08:   # TxDone
                self._write_reg(_REG_IRQ_FLAGS, 0xFF)
                self._set_mode(_MODE_RX_CONT)            # back to RX
                return True
            time.sleep(0.01)
        self._set_mode(_MODE_RX_CONT)
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
