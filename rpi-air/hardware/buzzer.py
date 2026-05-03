import RPi.GPIO as GPIO
from config import BUZZER_PIN, BUZZER_FREQ_HZ


class Buzzer:
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUZZER_PIN, GPIO.OUT, initial=GPIO.LOW)
        self._pwm = GPIO.PWM(BUZZER_PIN, BUZZER_FREQ_HZ)
        self._on = False

    def on(self):
        if not self._on:
            self._pwm.start(50)   # 50% duty cycle
            self._on = True

    def off(self):
        if self._on:
            self._pwm.stop()
            self._on = False

    @property
    def active(self) -> bool:
        return self._on

    def close(self):
        self.off()
        GPIO.cleanup(BUZZER_PIN)
