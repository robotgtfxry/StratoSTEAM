"""
Polls the backend for pending camera commands (photo request, recording toggle).
rpi-ground reads them before the next LoRa uplink window.
"""
import logging
import threading
import time
import requests
from config import BACKEND_URL, BACKEND_API_KEY

log = logging.getLogger(__name__)
_HEADERS = {"X-API-Key": BACKEND_API_KEY}


class CameraStore:
    def __init__(self):
        self._lock    = threading.Lock()
        self._photo   = False          # pending photo request
        self._rec     = None           # pending recording toggle (True/False) or None
        self._thread  = threading.Thread(target=self._poll, daemon=True)

    def start(self):
        self._thread.start()

    def _poll(self):
        while True:
            try:
                r = requests.get(
                    f"{BACKEND_URL}/api/camera/photo/pending",
                    headers=_HEADERS,
                    timeout=3,
                )
                if r.status_code == 200 and r.json().get("pending"):
                    with self._lock:
                        self._photo = True

                r2 = requests.get(
                    f"{BACKEND_URL}/api/camera/record/pending",
                    headers=_HEADERS,
                    timeout=3,
                )
                if r2.status_code == 200:
                    data = r2.json()
                    if data.get("pending"):
                        with self._lock:
                            self._rec = data["on"]

            except requests.RequestException as e:
                log.debug("Camera poll error: %s", e)

            time.sleep(1.0)

    def pop_photo(self) -> bool:
        """Returns True once if a photo was requested, then clears."""
        with self._lock:
            val = self._photo
            self._photo = False
            return val

    def pop_rec(self) -> bool | None:
        """Returns True/False if a recording toggle is pending, else None."""
        with self._lock:
            val = self._rec
            self._rec = None
            return val

    def post_chunk(self, packet: dict) -> None:
        """Forward a received image chunk to the backend (non-blocking, fire-and-forget)."""
        def _send():
            try:
                requests.post(
                    f"{BACKEND_URL}/api/camera/chunk",
                    json=packet,
                    headers=_HEADERS,
                    timeout=5,
                )
            except requests.RequestException as e:
                log.warning("Chunk upload error: %s", e)
        threading.Thread(target=_send, daemon=True).start()

    def post_storage(self, used_gb: float, free_gb: float) -> None:
        """Update disk usage on backend (non-blocking)."""
        def _send():
            try:
                requests.post(
                    f"{BACKEND_URL}/api/camera/storage",
                    json={"used_gb": used_gb, "free_gb": free_gb},
                    headers=_HEADERS,
                    timeout=5,
                )
            except requests.RequestException as e:
                log.debug("Storage update error: %s", e)
        threading.Thread(target=_send, daemon=True).start()
