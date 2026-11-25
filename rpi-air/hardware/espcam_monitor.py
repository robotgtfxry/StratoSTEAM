"""
ESP32-CAM status monitor — odczyt przez USB.

Kamera wysyła co ~5 s przez UART TX (GPIO1, 115200 baud) linię JSON
poprzedzoną prefiksem "$S":
  $S{"ok":1,"rec":1,"sd":1,"n":1234,"mb":7800,"fps":9.5}

Linie bez prefiksu (debug, komunikaty bootu) są ignorowane.

Połączenie: nakładka ESP32-CAM-MB (CH340) → kabel USB → RPi. Port "auto" wyszukuje
CH340, więc numer ttyUSB może się zmieniać, a kabel można wypiąć i wpiąć w trakcie pracy.
"""
import json
import logging
import threading
import time

log = logging.getLogger(__name__)

try:
    import serial
    from serial.tools import list_ports
    _SERIAL = True
except ImportError:
    _SERIAL = False
    log.warning("pyserial not available — EspCamMonitor disabled")

STATUS_TIMEOUT_S = 30   # po tym czasie bez statusu → kamera nieosiągalna
REOPEN_DELAY_S = 5      # ponowna próba otwarcia portu po błędzie

# Układy CH340/CH341 z nakładek ESP32-CAM-MB (VID, PID).
# Innych portów nie otwieramy na próbę: otwarcie portu może zresetować płytkę po drugiej
# stronie, a reset ESP32-S3 odcina zasilanie RPi.
CH340_IDS = {(0x1A86, 0x7523), (0x1A86, 0x7522), (0x1A86, 0x5523)}


def find_port(port: str) -> str:
    """Zwraca ścieżkę portu kamery. Dla "auto" szuka dokładnie jednego CH340."""
    if port != "auto":
        return port
    found = sorted(p.device for p in list_ports.comports() if (p.vid, p.pid) in CH340_IDS)
    if not found:
        raise OSError("nie widać kamery na USB (brak CH340) — sprawdź kabel: musi mieć linie danych")
    if len(found) > 1:
        raise OSError(f"kilka układów CH340 ({', '.join(found)}) — "
                      "wpisz ESPCAM_UART_PORT w rpi-air/config.py")
    return found[0]


def open_port(port: str, baud: int, timeout: float = 1.0):
    """
    Otwiera port kamery z DTR i RTS wyłączonymi. Na nakładce MB te linie idą do IO0 i EN —
    włączone trzymałyby kamerę w resecie albo w trybie wgrywania.
    """
    ser = serial.Serial(baudrate=baud, timeout=timeout)
    ser.port = find_port(port)
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser



class EspCamMonitor:
    """
    Czyta status ESP32-CAM z portu szeregowego.
    Wynik dostępny przez .compact() → [ok, rec, frames, free_mb]
    """

    def __init__(self, port: str, baud: int = 115200):
        self._port = port
        self._baud = baud
        self._status: dict = self._empty()
        self._last_seen: float | None = None   # time.monotonic() ostatniego statusu
        self._open_failed = False
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
            self._ser = open_port(self._port, self._baud)
            log.info("EspCamMonitor: listening on %s @ %d baud", self._ser.port, self._baud)
            self._open_failed = False
            return True
        except Exception as e:
            # tylko raz na awarię — próby są co REOPEN_DELAY_S, nie zaśmiecaj logu przez cały lot
            if not self._open_failed:
                log.error("EspCamMonitor: kamera niedostępna (%s) — ponawiam co %d s",
                          e, REOPEN_DELAY_S)
            self._open_failed = True
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
            if st:
                with self._lock:
                    self._status = st
                    self._last_seen = time.monotonic()
                log.debug("EspCam: ok=%s rec=%s sd=%s frames=%d free=%dMB fps=%.1f",
                          st["ok"], st["recording"], st["sd"],
                          st["frames"], st["free_mb"], st["fps"])

    def _reachable(self) -> bool:
        return (self._last_seen is not None
                and time.monotonic() - self._last_seen <= STATUS_TIMEOUT_S)

    def compact(self) -> list:
        """
        [ok, recording, frames, free_mb]
        Gotowe do osadzenia w pakiecie UART/LoRa jako pole "ec".
        Gdy kamera milczy dłużej niż STATUS_TIMEOUT_S, ok i recording = 0.
        """
        with self._lock:
            alive = self._reachable()
            return [
                1 if alive and self._status["ok"] else 0,
                1 if alive and self._status["recording"] else 0,
                self._status["frames"],
                self._status["free_mb"],
            ]

    def get(self) -> dict:
        with self._lock:
            return {**self._status, "reachable": self._reachable()}

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
