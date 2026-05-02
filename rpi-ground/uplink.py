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

    def _post(self, packet: dict) -> bool:
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
        except requests.RequestException as e:
            log.warning("Uplink error: %s", e)
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
            for pkt in pending:
                if not self._post(pkt):
                    still_pending.append(pkt)
            pending = still_pending

            if pending:
                log.info("%d packets buffered (offline?)", len(pending))
                time.sleep(OFFLINE_FLUSH_INTERVAL_S)
