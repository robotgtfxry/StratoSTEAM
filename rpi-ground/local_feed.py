"""
Lokalny podgląd odbioru: usługa rpi-ground zapisuje tu stan, okno gui_odbior.py go czyta.

  STATE_PATH — bieżący stan (w RAM, nadpisywany co ~1 s)
  LOG_DIR    — dziennik wszystkich odebranych pakietów (JSONL, jeden plik na dzień);
               zostaje na karcie nawet bez internetu
Błędy zapisu nigdy nie mogą zatrzymać odbioru.
"""
import json
import logging
import os
import time
from collections import deque

log = logging.getLogger(__name__)

STATE_PATH = os.environ.get("STRATO_STATE_PATH", "/dev/shm/stratosteam-ground.json")
LOG_DIR = os.path.expanduser(os.environ.get("STRATO_LOG_DIR", "~/stratosteam-odbior"))
HISTORY = 240           # punktów na wykresach


class LocalFeed:
    def __init__(self, state_path: str = STATE_PATH, log_dir: str = LOG_DIR):
        self._path = state_path
        self._log_dir = log_dir
        self._history: deque = deque(maxlen=HISTORY)
        self._warned = False
        self._state = {
            "started": time.time(), "packets": 0, "bad": 0, "img_chunks": 0, "lost": 0,
            "lora_resets": 0, "last": None, "last_rx": None, "rssi": None, "snr": None,
        }

    def packet(self, flat: dict, rssi: int, snr: float) -> None:
        """Poprawny pakiet telemetrii (rozwinięty beacon)."""
        st, now = self._state, time.time()
        prev, seq = (st["last"] or {}).get("seq"), flat.get("seq")
        if isinstance(prev, int) and isinstance(seq, int) and 1 < seq - prev < 10_000:
            st["lost"] += seq - prev - 1
        st["packets"] += 1
        st.update(last=flat, last_rx=now, rssi=rssi, snr=snr)
        alt = flat.get("alt") if flat.get("fix") else None
        self._history.append([now, alt, rssi])
        self._append({"rx": round(now, 2), "rssi": rssi, "snr": snr, "pkt": flat})

    def image_chunk(self) -> None:
        self._state["img_chunks"] += 1

    def bad(self) -> None:
        self._state["bad"] += 1

    def tick(self, lora_resets: int = 0) -> None:
        """Wołane w każdym obiegu pętli — znak życia dla okna."""
        self._state["lora_resets"] = lora_resets
        data = {**self._state, "alive": time.time(), "history": list(self._history)}
        tmp = f"{self._path}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self._path)
        except (OSError, TypeError, ValueError) as e:
            self._warn(e)

    def _append(self, rec: dict) -> None:
        try:
            os.makedirs(self._log_dir, exist_ok=True)
            name = time.strftime("odbior-%Y%m%d.jsonl")
            with open(os.path.join(self._log_dir, name), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        except (OSError, TypeError, ValueError) as e:
            self._warn(e)

    def _warn(self, e: Exception) -> None:
        if not self._warned:        # raz — nie zaśmiecaj logu przez cały lot
            log.warning("Podgląd lokalny niedostępny: %s", e)
            self._warned = True
