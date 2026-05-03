"""
Polls the backend for HF TX commands and drives the HF transmitter.
Runs in a background thread inside rpi-ground.
"""
import logging
import threading
import time
import requests
from config import BACKEND_URL, BACKEND_API_KEY, HF_POLL_INTERVAL_S
from radio.hf_tx import HfTransmitter

log = logging.getLogger(__name__)

_HEADERS = {"X-API-Key": BACKEND_API_KEY}


class HfController:
    def __init__(self):
        self._tx = HfTransmitter()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._stop_event = threading.Event()

    def start(self):
        self._thread.start()

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                r = requests.get(
                    f"{BACKEND_URL}/api/hf/command",
                    headers=_HEADERS,
                    timeout=3,
                )
                if r.status_code == 200:
                    cmd = r.json()
                    if cmd.get("action") == "start":
                        self._tx.start(int(cmd["freq_hz"]))
                    elif cmd.get("action") == "stop":
                        self._tx.stop()
                    elif cmd.get("action") == "set_freq":
                        self._tx.set_freq(int(cmd["freq_hz"]))
                    # report current status back
                    requests.post(
                        f"{BACKEND_URL}/api/hf/status",
                        json=self._tx.status,
                        headers=_HEADERS,
                        timeout=3,
                    )
            except requests.RequestException as e:
                log.debug("HF controller poll error: %s", e)
            self._stop_event.wait(HF_POLL_INTERVAL_S)

    def stop(self):
        self._stop_event.set()
        self._tx.close()
