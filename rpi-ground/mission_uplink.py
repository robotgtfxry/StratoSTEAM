"""Wysyła fazę misji (START, wznoszenie, …) na serwer, skąd czyta ją aplikacja."""
import logging
import threading
import time
import requests
from config import BACKEND_URL, BACKEND_API_KEY

log = logging.getLogger(__name__)
_HEADERS = {"X-API-Key": BACKEND_API_KEY}
INTERVAL_S = 5


class MissionUplink:
    def __init__(self):
        self._lock = threading.Lock()
        self._cur: tuple | None = None
        self._wake = threading.Event()
        self._warned = None

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def update(self, state: dict, auto: bool, last_rx: float | None, tcpu: float | None = None,
               cs: str | None = None) -> None:
        """Nie blokuje — wołane w każdym obiegu pętli radia."""
        with self._lock:
            changed = self._cur is None or self._cur[0]["phase"] != state["phase"] or self._cur[1] != auto
            self._cur = (state, auto, last_rx, tcpu, cs)
        if changed:
            self._wake.set()        # zmiana fazy idzie od razu

    def body(self) -> dict | None:
        with self._lock:
            if self._cur is None:
                return None
            st, auto, last_rx, tcpu, cs = self._cur
        now, t0 = time.time(), st.get("t0")

        def rnd(v):
            return None if v is None else round(v, 1)

        return {
            "phase": st["phase"], "elapsed": rnd(now - t0) if t0 else None,
            "alt": rnd(st.get("alt")), "vs": rnd(st.get("vs")), "max_alt": rnd(st.get("max_alt")),
            "src": st.get("src"), "auto": auto, "tcpu": tcpu, "cs": cs, "rx_age": rnd(now - last_rx) if last_rx else None,
            "events": [[rnd(t - t0), text[:160]] for t, text in st.get("events", []) if t0 and t >= t0][-8:],
        }

    def _run(self) -> None:
        while True:
            self._wake.wait(INTERVAL_S)
            self._wake.clear()
            try:
                body = self.body()
                if body is None:
                    continue
                r = requests.post(f"{BACKEND_URL}/api/mission", json=body, headers=_HEADERS, timeout=5)
                code = r.status_code
                if code != 200 and code != self._warned:     # np. 404 = stary serwer; loguj raz
                    log.warning("Faza misji: serwer odpowiedział %d", code)
                self._warned = code
            except requests.RequestException as e:
                log.debug("Faza misji: %s", e)
            except Exception:
                log.exception("Faza misji")
            time.sleep(1)           # nie częściej niż raz na sekundę
