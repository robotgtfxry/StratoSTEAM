"""
ESP32-CAM status monitor — odczyt przez sprzętowy UART RPi 5.

Kamera wysyła co ~5 s przez UART TX (GPIO1, 115200 baud) linię JSON
poprzedzoną prefiksem "$S":
  $S{"ok":1,"rec":1,"sd":1,"n":1234,"mb":7800,"fps":9.5}

Linie bez prefiksu (debug, komunikaty bootu) są ignorowane.

Połączenie: ESP32-CAM U0T (GPIO1) → RPi5 GPIO9 (pin 21) = UART3 RX.
Wymaga w /boot/firmware/config.txt:  dtoverlay=uart3-pi5   →  /dev/ttyAMA3
"""
import json
import logging
import threading
import time

log = logging.getLogger(__name__)

try:
    import serial
    _SERIAL = True
except ImportError:
    _SERIAL = False
    log.warning("pyserial not available — EspCamMonitor disabled")

STATUS_TIMEOUT_S = 30   # po tym czasie bez statusu → kamera nieosiągalna
REOPEN_DELAY_S = 5      # ponowna próba otwarcia portu po błędzie


class EspCamMonitor:
    """
    Czyta status ESP32-CAM z portu szeregowego.
    Wynik dostępny przez .compact() → [ok, rec, frames, free_mb]
    """

    def __init__(self, port: str, baud: int = 115200):
        self._port = port
        self._baud = baud
        self._status: dict = self._empty()
        self._last_seen = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._ser = None

        if not _SERIAL:
            return

        self._thread = threading.Thread(target=self._run, daemon=True, name="espcam-mon")
        self._thread.start()

    @staticmethod
    def _empty() -> dict:
        return {"ok": False, "recording": False, "sd": False,
                "frames": 0, "free_mb": 0, "fps": 0.0, "reachable": False}

    def _open(self) -> bool:
        try:
            self._ser = serial.Serial(self._port, self._baud, timeout=1.0)
            log.info("EspCamMonitor: listening on %s @ %d baud", self._port, self._baud)
            return True
        except Exception as e:
            log.error("EspCamMonitor: nie mogę otworzyć %s (%s) — "
                      "czy jest dtoverlay=uart3-pi5 w /boot/firmware/config.txt?", self._port, e)
            self._ser = None
            return False

    @staticmethod
    def parse_line(raw: bytes) -> dict | None:
        """Zwraca status z linii "$S{...}" albo None dla innych linii."""
        line = raw.decode("utf-8", errors="ignore").strip()
        idx = line.find("$S{")           # śmieci przed prefiksem (np. po resecie) są pomijane
        if idx < 0:
            return None
        try:
            j = json.loads(line[idx + 2:])
        except json.JSONDecodeError:
            log.debug("EspCam bad JSON: %r", line)
            return None
        return {
            "ok":        bool(j.get("ok", 0)),
            "recording": bool(j.get("rec", 0)),
            "sd":        bool(j.get("sd", 0)),
            "frames":    int(j.get("n", 0)),
            "free_mb":   int(j.get("mb", 0)),
            "fps":       float(j.get("fps", 0.0)),
            "reachable": True,
        }

    def _run(self):
        while not self._stop.is_set():
            if self._ser is None and not self._open():
                self._stop.wait(REOPEN_DELAY_S)
                continue

            try:
                raw = self._ser.readline()          # max 1 s (timeout)
            except Exception as e:
                log.warning("EspCam read error: %s — ponawiam otwarcie portu", e)
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None
                continue

            st = self.parse_line(raw) if raw else None
            with self._lock:
                if st:
                    self._status = st
                    self._last_seen = time.time()
                    log.debug("EspCam: ok=%s rec=%s sd=%s frames=%d free=%dMB fps=%.1f",
                              st["ok"], st["recording"], st["sd"],
                              st["frames"], st["free_mb"], st["fps"])
                elif self._last_seen > 0 and time.time() - self._last_seen > STATUS_TIMEOUT_S:
                    self._status["reachable"] = False

    def compact(self) -> list:
        """
        [ok, recording, frames, free_mb]
        Gotowe do osadzenia w pakiecie UART/LoRa jako pole "ec".
        """
        with self._lock:
            return [
                1 if self._status["ok"] else 0,
                1 if self._status["recording"] else 0,
                self._status["frames"],
                self._status["free_mb"],
            ]

    def get(self) -> dict:
        with self._lock:
            return dict(self._status)

    def stop(self):
        self._stop.set()
        if hasattr(self, "_thread"):
            self._thread.join(timeout=3)
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass
        log.info("EspCamMonitor stopped")
