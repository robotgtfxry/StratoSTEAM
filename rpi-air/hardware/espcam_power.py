"""
4× ESP32-CAM power control via N-MOSFET low-side switches.
RPi5 GPIO HIGH → MOSFET open → ESP-CAM powered.
"""
import logging
import RPi.GPIO as GPIO

log = logging.getLogger(__name__)


class EspCamPower:
    def __init__(self, pins: list[int]):
        self._pins = pins
        GPIO.setmode(GPIO.BCM)
        for p in self._pins:
            GPIO.setup(p, GPIO.OUT, initial=GPIO.LOW)
        log.info("EspCamPower ready, pins=%s (all OFF)", self._pins)

    def set(self, cam: int, on: bool) -> None:
        """Power cam on/off. cam=-1 affects all cameras."""
        if cam == -1:
            for p in self._pins:
                GPIO.output(p, GPIO.HIGH if on else GPIO.LOW)
            log.info("EspCam ALL %s", "ON" if on else "OFF")
        elif 0 <= cam < len(self._pins):
            GPIO.output(self._pins[cam], GPIO.HIGH if on else GPIO.LOW)
            log.info("EspCam %d %s", cam, "ON" if on else "OFF")
        else:
            log.warning("EspCam invalid index: %d", cam)

    def state(self) -> list[bool]:
        return [bool(GPIO.input(p)) for p in self._pins]

    def close(self) -> None:
        for p in self._pins:
            GPIO.output(p, GPIO.LOW)
        GPIO.cleanup(self._pins)
