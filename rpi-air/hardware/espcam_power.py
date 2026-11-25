"""
ESP32-CAM power control.

Domyślnie kamera jest podłączona BEZPOŚREDNIO do 5V RPi (zawsze zasilona)
— wtedy pin = None i komenda "espcam_pwr" jest tylko logowana.

Opcjonalnie: N-MOSFET low-side switch (GPIO HIGH → MOSFET otwarty → kamera zasilona).
"""
import logging

log = logging.getLogger(__name__)


class EspCamPower:
    def __init__(self, pin: int | None):
        self._pin = pin
        if pin is None:
            log.info("EspCamPower: kamera zasilana bezpośrednio z 5V (bez przełączania)")
            return
        import RPi.GPIO as GPIO
        self._gpio = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self._pin, GPIO.OUT, initial=GPIO.HIGH)
        log.info("EspCamPower ready, pin=GPIO%d (ON)", self._pin)

    def set(self, on: bool) -> None:
        if self._pin is None:
            log.warning("espcam_pwr on=%s zignorowane — kamera podłączona na stałe do 5V", on)
            return
        self._gpio.output(self._pin, self._gpio.HIGH if on else self._gpio.LOW)
        log.info("EspCam %s", "ON" if on else "OFF")

    def state(self) -> bool:
        if self._pin is None:
            return True
        return bool(self._gpio.input(self._pin))

    def close(self) -> None:
        if self._pin is None:
            return
        self._gpio.cleanup(self._pin)
