"""
Lokalny podgląd odbioru: usługa rpi-ground zapisuje tu stan, okno gui_odbior.py go czyta.

  STATE_PATH — bieżący stan (w RAM, nadpisywany co ~1 s)
  LOG_DIR    — dziennik wszystkich odebranych pakietów (JSONL, jeden plik na dzień);
               zostaje na karcie nawet bez internetu
Błędy zapisu nigdy nie mogą zatrzymać odbioru.
"""
import base64
import json
import logging
import os
import time
from collections import deque

log = logging.getLogger(__name__)

STATE_PATH = os.environ.get("STRATO_STATE_PATH", "/dev/shm/stratosteam-ground.json")
LOG_DIR = os.path.expanduser(os.environ.get("STRATO_LOG_DIR", "~/stratosteam-odbior"))
PHOTO_PATH = os.environ.get("STRATO_PHOTO_PATH", "/dev/shm/stratosteam-photo.jpg")
REQUEST_PATH = os.environ.get("STRATO_REQUEST_PATH", "/dev/shm/stratosteam-photo.req")
AUTO_PATH = os.environ.get("STRATO_AUTO_PATH", "/dev/shm/stratosteam-photo.auto")
AUTO_S = 180            # automatyczne zdjęcie co tyle sekund (gdy plik AUTO_PATH istnieje)
RETRY_S = 40            # brak fragmentów po prośbie → ponów
MAX_TRIES = 3
PHOTO_MAX_CHUNKS = 200
PHOTO_GAP_S = 60        # ta sama nr zdjęcia po takiej przerwie = nowe zdjęcie (restart balonu)
HISTORY = 240           # punktów na wykresach


class LocalFeed:
    def __init__(self, state_path: str = STATE_PATH, log_dir: str = LOG_DIR):
        self._path = state_path
        self._log_dir = log_dir
        self._chunks: dict[int, bytes] = {}
        self._last_req = 0.0
        self._history: deque = deque(maxlen=HISTORY)
        self._warned = False
        self._state = {
            "started": time.time(), "packets": 0, "bad": 0, "img_chunks": 0, "lost": 0,
            "lora_resets": 0, "photo": None, "photo_req": None, "photo_try": 0,
            "photo_fail": None, "last": None, "last_rx": None, "rssi": None, "snr": None,
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

    def image_chunk(self, packet: dict) -> None:
        """Składa zdjęcie. Niepełne też pokazuje — JPEG da się otworzyć od początku."""
        self._state["img_chunks"] += 1
        try:
            img_id, seq, total = int(packet["id"]), int(packet["seq"]), int(packet["tot"])
            data = base64.b64decode(packet["data"], validate=True)
        except (KeyError, TypeError, ValueError):
            return
        if not (0 < total <= PHOTO_MAX_CHUNKS and 0 <= seq < total):
            return
        now, ph = time.time(), self._state["photo"]
        if not ph or ph["id"] != img_id or ph["total"] != total or now - ph["ts"] > PHOTO_GAP_S:
            ph = self._state["photo"] = {"id": img_id, "total": total, "got": 0,
                                         "done": False, "ts": now}
            self._chunks = {}
            self._state.update(photo_req=None, photo_fail=None)
        ph["ts"] = now
        if ph["done"] or seq in self._chunks:
            return
        self._chunks[seq] = data
        ph["got"] = len(self._chunks)
        ph["done"] = ph["got"] == total
        prefix = b""
        for i in range(total):
            if i not in self._chunks:
                break
            prefix += self._chunks[i]
        if prefix:
            self._write(PHOTO_PATH, prefix)
        if ph["done"]:
            self._write(os.path.join(self._log_dir, time.strftime("foto-%Y%m%d-%H%M%S.jpg")), prefix)

    def pop_photo(self) -> bool:
        """Czy wysłać teraz prośbę o zdjęcie: kliknięcie, ponowienie albo tryb automatyczny."""
        st, now = self._state, time.time()
        try:
            os.remove(REQUEST_PATH)
            clicked = True
        except OSError:
            clicked = False

        if clicked:
            st["photo_try"] = 0
        elif st["photo_req"]:
            if now - self._last_req < RETRY_S:
                return False
            if st["photo_try"] >= MAX_TRIES:        # RPi balonu nie odpowiada
                st.update(photo_req=None, photo_fail=now)
                return False
        else:
            receiving = st["photo"] and now - st["photo"]["ts"] < RETRY_S
            if receiving or not os.path.exists(AUTO_PATH) or now - self._last_req < AUTO_S:
                return False
            st["photo_try"] = 0
        st["photo_try"] += 1
        st["photo_req"] = st["photo_req"] if st["photo_try"] > 1 else now
        st["photo_fail"] = None
        self._last_req = now
        return True

    def _write(self, path: str, data: bytes) -> None:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + ".tmp", "wb") as f:
                f.write(data)
            os.replace(path + ".tmp", path)
        except OSError as e:
            self._warn(e)

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
