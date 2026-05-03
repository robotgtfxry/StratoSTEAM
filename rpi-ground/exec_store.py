"""
Polls backend for pending exec commands, posts results received from rpi-air.
"""
import logging
import threading
import time
import requests
from config import BACKEND_URL, BACKEND_API_KEY

log = logging.getLogger(__name__)
_HEADERS = {"X-API-Key": BACKEND_API_KEY}


class ExecStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._pending_sh: str | None = None
        self._thread = threading.Thread(target=self._poll, daemon=True)

    def start(self):
        self._thread.start()

    def _poll(self):
        while True:
            try:
                r = requests.get(
                    f"{BACKEND_URL}/api/exec/pending",
                    headers=_HEADERS, timeout=3,
                )
                if r.status_code == 200:
                    data = r.json()
                    if data.get("has_command"):
                        with self._lock:
                            self._pending_sh = data["sh"]
            except requests.RequestException as e:
                log.debug("Exec poll error: %s", e)
            time.sleep(1.0)

    def pop(self) -> str | None:
        with self._lock:
            sh = self._pending_sh
            self._pending_sh = None
            return sh

    def post_result(self, rc: int, out: str, err: str):
        try:
            requests.post(
                f"{BACKEND_URL}/api/exec/result",
                headers={**_HEADERS, "Content-Type": "application/json"},
                json={"rc": rc, "out": out, "err": err},
                timeout=3,
            )
        except requests.RequestException as e:
            log.debug("Exec result post error: %s", e)
