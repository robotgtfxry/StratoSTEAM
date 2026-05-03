import RPi.GPIO as GPIO
from config import LED_R_PIN, LED_G_PIN, LED_B_PIN


class RgbLed:
    """
    Common-cathode RGB LED on 3 GPIO pins.
    Color expressed as (r, g, b) each 0-255, mapped to PWM duty cycle.
    """

    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        for pin in (LED_R_PIN, LED_G_PIN, LED_B_PIN):
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
        self._r = GPIO.PWM(LED_R_PIN, 1000)
        self._g = GPIO.PWM(LED_G_PIN, 1000)
        self._b = GPIO.PWM(LED_B_PIN, 1000)
        self._r.start(0)
        self._g.start(0)
        self._b.start(0)
        self._color = (0, 0, 0)

    def set_color(self, r: int, g: int, b: int):
        r, g, b = max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))
        self._r.ChangeDutyCycle(r / 255 * 100)
        self._g.ChangeDutyCycle(g / 255 * 100)
        self._b.ChangeDutyCycle(b / 255 * 100)
        self._color = (r, g, b)

    def off(self):
        self.set_color(0, 0, 0)

    @property
    def color(self) -> tuple[int, int, int]:
        return self._color

    def close(self):
        self.off()
        self._r.stop()
        self._g.stop()
        self._b.stop()
        GPIO.cleanup([LED_R_PIN, LED_G_PIN, LED_B_PIN])
