"""
Forwards received telemetry packets to the backend.
Queues packets locally when offline and retries.
"""
import json
import logging
import queue
import threading
import time
import requests
from config import BACKEND_URL, BACKEND_API_KEY, OFFLINE_FLUSH_INTERVAL_S

log = logging.getLogger(__name__)

_HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": BACKEND_API_KEY,
}


class Uplink:
    def __init__(self):
        self._q: queue.Queue[dict] = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def send(self, packet: dict, rssi: int, snr: float):
        """Queue a packet for upload (non-blocking)."""
        packet["rssi"] = rssi
        packet["snr"] = round(snr, 1)
        self._q.put(packet)

    def _post(self, packet: dict) -> bool | None:
        """True = przyjęty, False = serwer odmówił, None = brak połączenia."""
        try:
            r = requests.post(
                f"{BACKEND_URL}/api/telemetry",
                data=json.dumps(packet),
                headers=_HEADERS,
                timeout=5,
            )
            if r.status_code == 201:
                return True
            log.warning("Backend returned %d: %s", r.status_code, r.text[:200])
            if r.status_code in (400, 422):
                log.error("Pakiet odrzucony na stałe (seq=%s) — nie ponawiam", packet.get("seq"))
                return True
        except requests.RequestException as e:
            log.warning("Uplink error: %s", e)
            return None
        return False

    def _worker(self):
        pending: list[dict] = []
        while True:
            # drain queue into pending
            try:
                while True:
                    pending.append(self._q.get_nowait())
            except queue.Empty:
                pass

            if not pending:
                time.sleep(0.5)
                continue

            # try to flush
            still_pending = []
            for i, pkt in enumerate(pending):
                ok = self._post(pkt)
                if ok is None:              # brak sieci: reszta też nie przejdzie
                    still_pending += pending[i:]
                    break
                if not ok:
                    still_pending.append(pkt)
            pending = still_pending

            if pending:
                log.info("%d packets buffered (offline?)", len(pending))
                time.sleep(OFFLINE_FLUSH_INTERVAL_S)
