"""
Polls backend for RPi power commands, reports actual RPi running state.
"""
import json
import logging
import threading
import time
import requests
from config import BACKEND_URL, BACKEND_API_KEY

log = logging.getLogger(__name__)
_HEADERS = {"X-API-Key": BACKEND_API_KEY}


class RpiPowerStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._pending_on: bool | None = None
        self._running: bool | None = None      # ostatni stan do wysłania
        self._changed = threading.Event()
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._reporter = threading.Thread(target=self._report_loop, daemon=True)

    def start(self):
        self._thread.start()
        self._reporter.start()

    def _poll(self):
        while True:
            try:
                r = requests.get(
                    f"{BACKEND_URL}/api/rpi_power/pending",
                    headers=_HEADERS,
                    timeout=3,
                )
                if r.status_code == 200:
                    data = r.json()
                    if data.get("has_command"):
                        with self._lock:
                            self._pending_on = bool(data["on"])
            except requests.RequestException as e:
                log.debug("RpiPower poll error: %s", e)
            time.sleep(1.0)

    def pop(self) -> bool | None:
        """Return and clear pending power command (True=on, False=off, None=nothing)."""
        with self._lock:
            val = self._pending_on
            self._pending_on = None
            return val

    def report_status(self, rpi_running: bool):
        """Nie blokuje — wołane z pętli odbioru radia, a sieć potrafi wisieć kilka sekund."""
        with self._lock:
            self._running = rpi_running
        self._changed.set()

    def _report_loop(self):
        while True:
            self._changed.wait()
            self._changed.clear()
            with self._lock:
                running = self._running
            self._post_status(running)

    def _post_status(self, rpi_running: bool):
        try:
            requests.post(
                f"{BACKEND_URL}/api/rpi_power/status",
                headers={**_HEADERS, "Content-Type": "application/json"},
                json={"rpi_running": rpi_running},
                timeout=3,
            )
        except requests.RequestException as e:
            log.debug("RpiPower status report error: %s", e)
