"""
ESP32-CAM status monitor — odczyt przez UART (pigpio bit-bang serial).

Kamera wysyła co ~5 s przez UART TX (GPIO1, 115200 baud) linię JSON
poprzedzoną prefiksem "$S":
  $S{"ok":1,"rec":1,"n":1234,"mb":7800}

Linie bez prefiksu (debug, komunikaty bootu) są ignorowane.
RPi odbiera na GPIO4. Nie wymaga WiFi — tylko kabel TX→GPIO.

UWAGA: pigpio nie wspiera Raspberry Pi 5. Na RPi 5 ten odczyt trzeba przenieść
na lgpio albo na sprzętowy UART — monitor zgłosi wtedy brak pigpio i zostanie
wyłączony (reszta telemetrii działa normalnie).
"""
import json
import logging
import threading
import time

log = logging.getLogger(__name__)

try:
    import pigpio
    _PIGPIO = True
except ImportError:
    _PIGPIO = False
    log.warning("pigpio not available — EspCamMonitor disabled")

READ_INTERVAL_S = 0.2   # jak często sprawdzamy bufor
STATUS_TIMEOUT_S = 30   # po tym czasie status = nieaktywny


class EspCamMonitor:
    """
    Czyta status ESP32-CAM przez bit-bang serial (pigpio).
    Wynik dostępny przez .compact() → [ok, rec, frames, free_mb]
    """

    def __init__(self, pin: int, baud: int = 115200):
        self._pin = pin
        self._baud = baud
        self._status: dict = self._empty()
        self._last_seen = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._pi = None
        self._rx_buf = ""

        if not _PIGPIO:
            return

        self._pi = pigpio.pi()
        if not self._pi.connected:
            log.error("pigpio daemon not running — EspCamMonitor disabled")
            self._pi = None
            return

        err = self._pi.bb_serial_read_open(pin, baud, 8)
        if err != 0:
            log.error("bb_serial_read_open failed pin=%d err=%d", pin, err)
            self._pi = None
            return
        log.info("EspCamMonitor: listening on GPIO%d @ %d baud", pin, baud)

        self._thread = threading.Thread(target=self._run, daemon=True, name="espcam-mon")
        self._thread.start()

    @staticmethod
    def _empty() -> dict:
        return {"ok": False, "recording": False,
                "frames": 0, "free_mb": 0, "reachable": False}

    def _run(self):
        while not self._stop.is_set():
            if self._pi is None:
                self._stop.wait(1.0)
                continue

            try:
                count, data = self._pi.bb_serial_read(self._pin)
            except Exception as e:
                log.debug("EspCam read error: %s", e)
                count, data = 0, b""

            if count > 0:
                self._rx_buf += data.decode("utf-8", errors="ignore")
                # Ogranicz bufor żeby nie rósł w nieskończoność przy śmieciach
                if len(self._rx_buf) > 2048:
                    self._rx_buf = self._rx_buf[-512:]
                # Parsuj tylko linie zaczynające się od "$S" (reszta = debug/boot)
                while "\n" in self._rx_buf:
                    line, self._rx_buf = self._rx_buf.split("\n", 1)
                    line = line.strip()
                    if not line.startswith("$S"):
                        continue  # ignoruj debug i boot messages
                    line = line[2:]  # odetnij prefix "$S"
                    try:
                        j = json.loads(line)
                    except json.JSONDecodeError:
                        log.debug("EspCam bad JSON: %r", line)
                        continue
                    st = {
                        "ok":        bool(j.get("ok", 0)),
                        "recording": bool(j.get("rec", 0)),
                        "frames":    int(j.get("n", 0)),
                        "free_mb":   int(j.get("mb", 0)),
                        "reachable": True,
                    }
                    with self._lock:
                        self._status = st
                        self._last_seen = time.time()
                    log.debug("EspCam: ok=%s rec=%s frames=%d free=%dMB",
                              st["ok"], st["recording"], st["frames"], st["free_mb"])

            # Oznacz kamerę jako nieosiągalną po timeoucie
            with self._lock:
                if self._last_seen > 0 and time.time() - self._last_seen > STATUS_TIMEOUT_S:
                    self._status["reachable"] = False

            self._stop.wait(READ_INTERVAL_S)

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
        if self._pi:
            try:
                self._pi.bb_serial_read_close(self._pin)
            except Exception:
                pass
            self._pi.stop()
        log.info("EspCamMonitor stopped")
