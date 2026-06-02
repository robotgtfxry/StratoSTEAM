"""
ESP32-CAM status monitor — odczyt przez UART (pigpio bit-bang serial).

Każda kamera wysyła co ~5 s przez UART TX (GPIO1, 9600 baud) linię JSON:
  {"c":0,"ok":1,"rec":1,"n":1234,"mb":7800}

RPi odbiera na GPIO 4/7/8/9 (po jednym na kamerę).
Nie wymaga WiFi — tylko kabel TX→GPIO.
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
    Czyta statusy ESP32-CAM przez bit-bang serial (pigpio).
    Wyniki dostępne przez .compact() → [[ok,rec,frames,free_mb], ...]
    """

    def __init__(self, pins: list[int], baud: int = 9600):
        self._pins = pins
        self._baud = baud
        self._count = len(pins)
        self._statuses: list[dict] = [self._empty(i) for i in range(self._count)]
        self._last_seen: list[float] = [0.0] * self._count
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._pi = None
        self._rx_bufs: list[str] = [""] * self._count

        if not _PIGPIO:
            return

        self._pi = pigpio.pi()
        if not self._pi.connected:
            log.error("pigpio daemon not running — EspCamMonitor disabled")
            self._pi = None
            return

        for i, pin in enumerate(self._pins):
            err = self._pi.bb_serial_read_open(pin, baud, 8)
            if err != 0:
                log.error("bb_serial_read_open failed pin=%d err=%d", pin, err)
            else:
                log.info("EspCamMonitor: CAM %d listening on GPIO%d @ %d baud", i, pin, baud)

        self._thread = threading.Thread(target=self._run, daemon=True, name="espcam-mon")
        self._thread.start()

    @staticmethod
    def _empty(cam: int) -> dict:
        return {"cam": cam, "ok": False, "recording": False,
                "frames": 0, "free_mb": 0, "reachable": False}

    def _run(self):
        while not self._stop.is_set():
            if self._pi is None:
                self._stop.wait(1.0)
                continue

            for i, pin in enumerate(self._pins):
                try:
                    count, data = self._pi.bb_serial_read(pin)
                except Exception as e:
                    log.debug("CAM %d read error: %s", i, e)
                    continue

                if count > 0:
                    self._rx_bufs[i] += data.decode("utf-8", errors="ignore")
                    # Ogranicz bufor żeby nie rósł w nieskończoność przy śmieciach
                    if len(self._rx_bufs[i]) > 2048:
                        self._rx_bufs[i] = self._rx_bufs[i][-512:]
                    # Parsuj tylko linie zaczynające się od "$S" (reszta = debug/boot)
                    while "\n" in self._rx_bufs[i]:
                        line, self._rx_bufs[i] = self._rx_bufs[i].split("\n", 1)
                        line = line.strip()
                        if not line.startswith("$S"):
                            continue  # ignoruj debug i boot messages
                        line = line[2:]  # odetnij prefix "$S"
                        try:
                            j = json.loads(line)
                            st = {
                                "cam":       i,
                                "ok":        bool(j.get("ok", 0)),
                                "recording": bool(j.get("rec", 0)),
                                "frames":    int(j.get("n", 0)),
                                "free_mb":   int(j.get("mb", 0)),
                                "reachable": True,
                            }
                            with self._lock:
                                self._statuses[i] = st
                                self._last_seen[i] = time.time()
                            log.debug("CAM %d: ok=%s rec=%s frames=%d free=%dMB",
                                      i, st["ok"], st["recording"],
                                      st["frames"], st["free_mb"])
                        except json.JSONDecodeError:
                            log.debug("CAM %d bad JSON: %r", i, line)

            # Oznacz kamery jako nieosiągalne po timeoucie
            now = time.time()
            with self._lock:
                for i in range(self._count):
                    if self._last_seen[i] > 0 and now - self._last_seen[i] > STATUS_TIMEOUT_S:
                        self._statuses[i]["reachable"] = False

            self._stop.wait(READ_INTERVAL_S)

    def compact(self) -> list[list]:
        """
        [[ok, recording, frames, free_mb], ...]  (4 listy)
        Gotowe do osadzenia w pakiecie UART/LoRa jako pole "ec".
        """
        with self._lock:
            return [
                [
                    1 if s["ok"] else 0,
                    1 if s["recording"] else 0,
                    s["frames"],
                    s["free_mb"],
                ]
                for s in self._statuses
            ]

    def get_all(self) -> list[dict]:
        with self._lock:
            return [dict(s) for s in self._statuses]

    def stop(self):
        self._stop.set()
        if hasattr(self, "_thread"):
            self._thread.join(timeout=3)
        if self._pi:
            for pin in self._pins:
                try:
                    self._pi.bb_serial_read_close(pin)
                except Exception:
                    pass
            self._pi.stop()
        log.info("EspCamMonitor stopped")
