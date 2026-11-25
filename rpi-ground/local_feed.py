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
PHOTO_PATH = os.environ.get("STRATO_PHOTO_PATH", "/dev/shm/stratosteam-photo.webp")
CMD_DIR = os.environ.get("STRATO_CMD_DIR", "/dev/shm/stratosteam-cmd")
REQUEST_PATH = os.environ.get("STRATO_REQUEST_PATH", "/dev/shm/stratosteam-photo.req")
# na karcie, nie w RAM — automatyczne zdjęcia mają przetrwać restart stacji w locie
AUTO_PATH = os.environ.get("STRATO_AUTO_PATH", os.path.join(LOG_DIR, "auto-zdjecia"))
AUTO_S = 180            # automatyczne zdjęcie co tyle sekund (gdy plik AUTO_PATH istnieje)
RETRY_S = 40            # brak fragmentów po prośbie → ponów
MAX_TRIES = 3
HISTORY = 240           # punktów na wykresach


class LocalFeed:
    def __init__(self, state_path: str = STATE_PATH, log_dir: str = LOG_DIR):
        self._path = state_path
        self._log_dir = log_dir
        self._last_req = 0.0
        self._history: deque = deque(maxlen=HISTORY)
        self._warned = False
        self._state = {
            "started": time.time(), "packets": 0, "bad": 0, "lost": 0,
            "lora_resets": 0, "photo": None, "mission": None, "buzzer": None, "lora_reset_at": None, "photo_req": None, "photo_try": 0,
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

    def photo_progress(self, state: dict | None) -> None:
        st = self._state
        if state and (not st["photo"] or st["photo"]["id"] != state["id"]):
            st.update(photo_req=None, photo_fail=None)      # balon odpowiedział
        st["photo"] = state

    def photo_done(self, blob: bytes) -> str:
        """Całe, sprawdzone zdjęcie. Zwraca ścieżkę pliku na karcie."""
        self._write(PHOTO_PATH, blob)
        path = os.path.join(self._log_dir, time.strftime("foto-%Y%m%d-%H%M%S.webp"))
        self._write(path, blob)
        return path

    @property
    def last_rx(self) -> float | None:
        return self._state["last_rx"]

    @property
    def tcpu(self) -> float | None:
        """Temperatura procesora RPi balonu z ostatniego pakietu."""
        return (self._state["last"] or {}).get("tcpu")

    @staticmethod
    def auto_on() -> bool:
        return os.path.exists(AUTO_PATH)

    @staticmethod
    def set_auto(on: bool) -> None:
        try:
            if on:
                os.makedirs(os.path.dirname(AUTO_PATH), exist_ok=True)
                open(AUTO_PATH, "w").close()
            elif os.path.exists(AUTO_PATH):
                os.remove(AUTO_PATH)
            log.info("Automatyczne zdjęcia: %s", "włączone" if on else "wyłączone")
        except OSError as e:
            log.warning("Automatyczne zdjęcia: %s", e)

    def buzzer(self, text: str) -> None:
        self._state["buzzer"] = {"text": text, "ts": time.time()}

    def mission(self, state: dict) -> None:
        self._state["mission"] = state

    @staticmethod
    def commands() -> list[dict]:
        """Polecenia z okna (pliki JSON w CMD_DIR), w kolejności wysłania."""
        out = []
        try:
            names = sorted(n for n in os.listdir(CMD_DIR) if n.endswith(".json"))
        except OSError:
            return out
        for n in names:
            path = os.path.join(CMD_DIR, n)
            try:
                with open(path, encoding="utf-8") as f:
                    c = json.load(f)
                if isinstance(c, dict):
                    out.append(c)
            except (OSError, ValueError):
                pass
            try:
                os.remove(path)
            except OSError:
                pass
        return out

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
            ph = st["photo"]
            receiving = ph and not ph["done"] and not ph["failed"]
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
        if lora_resets > self._state["lora_resets"]:
            self._state["lora_reset_at"] = time.time()
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
