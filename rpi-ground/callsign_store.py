"""
Znak wywoławczy sondy ustawiany w aplikacji. Stacja pyta serwer o żądany znak i nadaje
go sondzie, aż beacon przyjdzie z nowym znakiem (łącze nie ma potwierdzeń).
"""
import logging
import threading
import time
import requests
from config import BACKEND_URL, BACKEND_API_KEY

log = logging.getLogger(__name__)
_HEADERS = {"X-API-Key": BACKEND_API_KEY}
POLL_S = 10
RETRY_S = 20        # co tyle ponawiać, póki beacon nie pokaże nowego znaku
MAX_TRIES = 15


class CallsignStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._desired: str | None = None
        self._tries = 0
        self._last = 0.0

    def start(self) -> None:
        threading.Thread(target=self._poll, daemon=True).start()

    def _poll(self) -> None:
        while True:
            try:
                r = requests.get(f"{BACKEND_URL}/api/callsign", headers=_HEADERS, timeout=5)
                if r.status_code == 200:
                    self.set_desired(r.json().get("desired"))
            except (requests.RequestException, ValueError) as e:
                log.debug("Znak wywoławczy: %s", e)
            time.sleep(POLL_S)

    def set_desired(self, cs: str | None) -> None:
        with self._lock:
            if cs != self._desired:
                self._desired, self._tries, self._last = cs, 0, 0.0
                if cs:
                    log.info("Znak wywoławczy sondy do ustawienia: %s", cs)

    def pop(self, current: str | None) -> str | None:
        """Znak do nadania teraz albo None (już ustawiony, za wcześnie, za dużo prób)."""
        with self._lock:
            want = self._desired
            if not want or want == current or self._tries >= MAX_TRIES \
                    or time.monotonic() - self._last < RETRY_S:
                if want and want == current and self._tries:
                    log.info("Sonda nadaje już jako %s", want)
                    self._tries = 0
                return None
            self._tries += 1
            self._last = time.monotonic()
            return want
