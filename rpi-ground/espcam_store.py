"""
Polls the backend for a pending ESP32-CAM power command.
rpi-ground reads it before the next LoRa uplink window.
"""
import logging
import threading
import time
import requests
from config import BACKEND_URL, BACKEND_API_KEY

log = logging.getLogger(__name__)
_HEADERS = {"X-API-Key": BACKEND_API_KEY}


class EspCamStore:
    def __init__(self):
        self._lock    = threading.Lock()
        self._pending: bool | None = None      # żądany stan zasilania kamery
        self._thread  = threading.Thread(target=self._poll, daemon=True)

    def start(self):
        self._thread.start()

    def _poll(self):
        while True:
            try:
                r = requests.get(
                    f"{BACKEND_URL}/api/espcam/power/pending",
                    headers=_HEADERS,
                    timeout=3,
                )
                if r.status_code == 200:
                    data = r.json()
                    if data.get("pending"):
                        with self._lock:
                            self._pending = bool(data["on"])
            except requests.RequestException as e:
                log.debug("EspCam poll error: %s", e)
            time.sleep(1.0)

    def pop(self) -> bool | None:
        """Zwraca żądany stan zasilania jeśli czeka komenda, inaczej None."""
        with self._lock:
            val = self._pending
            self._pending = None
            return val
