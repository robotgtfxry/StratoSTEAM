"""
ESP32-CAM power control via an N-MOSFET low-side switch.
RPi5 GPIO HIGH → MOSFET open → ESP-CAM powered.
"""
import logging
import RPi.GPIO as GPIO

log = logging.getLogger(__name__)


class EspCamPower:
    def __init__(self, pin: int):
        self._pin = pin
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self._pin, GPIO.OUT, initial=GPIO.LOW)
        log.info("EspCamPower ready, pin=GPIO%d (OFF)", self._pin)

    def set(self, on: bool) -> None:
        GPIO.output(self._pin, GPIO.HIGH if on else GPIO.LOW)
        log.info("EspCam %s", "ON" if on else "OFF")

    def state(self) -> bool:
        return bool(GPIO.input(self._pin))

    def close(self) -> None:
        GPIO.output(self._pin, GPIO.LOW)
        GPIO.cleanup(self._pin)
