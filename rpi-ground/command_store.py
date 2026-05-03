"""
Polls the backend for pending uplink commands and stores the latest one.
rpi-ground reads it before sending a command packet to the balloon.
"""
import logging
import threading
import time
import requests
from config import BACKEND_URL, BACKEND_API_KEY

log = logging.getLogger(__name__)
_HEADERS = {"X-API-Key": BACKEND_API_KEY}


class CommandStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._pending: dict | None = None   # command waiting to be sent
        self._thread = threading.Thread(target=self._poll, daemon=True)

    def start(self):
        self._thread.start()

    def _poll(self):
        while True:
            try:
                r = requests.get(
                    f"{BACKEND_URL}/api/commands/pending",
                    headers=_HEADERS,
                    timeout=3,
                )
                if r.status_code == 200:
                    data = r.json()
                    if data.get("has_command"):
                        with self._lock:
                            self._pending = data["command"]
            except requests.RequestException as e:
                log.debug("Command poll error: %s", e)
            time.sleep(1.0)

    def pop(self) -> dict | None:
        """Return and clear the pending command (call before each TX window)."""
        with self._lock:
            cmd = self._pending
            self._pending = None
            return cmd
