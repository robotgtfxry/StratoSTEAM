"""
Sygnały GPIO między RPi a ESP32-S3.
  RPI_ALIVE_PIN  — RPi trzyma HIGH póki działa; ESP32 monitoruje
  ESP32_SHTDN_PIN — ESP32 podnosi HIGH gdy chce żeby RPi się wyłączyła
"""
import RPi.GPIO as GPIO
from config import RPI_ALIVE_PIN, ESP32_SHTDN_PIN


class PowerSignal:
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(RPI_ALIVE_PIN,   GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(ESP32_SHTDN_PIN, GPIO.IN,  pull_up_down=GPIO.PUD_DOWN)

    def set_alive(self, on: bool):
        GPIO.output(RPI_ALIVE_PIN, GPIO.HIGH if on else GPIO.LOW)

    @property
    def shutdown_requested(self) -> bool:
        return GPIO.input(ESP32_SHTDN_PIN) == GPIO.HIGH

    def close(self):
        GPIO.output(RPI_ALIVE_PIN, GPIO.LOW)
        GPIO.cleanup([RPI_ALIVE_PIN, ESP32_SHTDN_PIN])
