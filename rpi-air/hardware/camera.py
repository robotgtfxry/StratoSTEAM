"""
Camera module: continuous H.264 recording to disk + on-demand photo capture.
Photos are compressed to WebP small enough for one LoRa burst (see esp32/src/main.cpp).
"""
import io
import logging
import os
import shutil
import threading
import time
from datetime import datetime

log = logging.getLogger(__name__)

try:
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import Output
    _PICAM2 = True
except ImportError:
    _PICAM2 = False

    class Output:                   # zastępczo, gdy picamera2 brak (testy na PC)
        def start(self):
            pass

        def stop(self):
            pass

    log.warning("picamera2 not available — camera disabled")

try:
    from PIL import Image as _PilImage
    _PIL = True
except ImportError:
    _PIL = False


def free_gb(path: str) -> float:
    try:
        return shutil.disk_usage(path).free / 1e9
    except OSError:
        return 0.0


class SegmentOutput(Output):
    """
    Zapis H.264 w kawałkach po segment_s, cięty na klatce kluczowej — koder powtarza
    nagłówki przy każdej, więc każdy plik odtwarza się sam. Gdy wolnego miejsca jest
    mniej niż min_free_gb, zapis czeka (co 30 s sprawdza ponownie).
    Wołane z wątku kodera: wyjątek nie może stąd wyjść, bo zatrzymałby nagrywanie.
    """

    def __init__(self, directory: str, segment_s: int, min_free_gb: float):
        super().__init__()
        self._dir = directory
        self._seg_s = segment_s
        self._min_free = min_free_gb
        self._lock = threading.Lock()
        self._fh = None
        self._opened = 0.0
        self._checked = -1e9        # ostatnia nieudana próba (brak miejsca / błąd)
        self.path: str | None = None
        self.full = False

    @property
    def writing(self) -> bool:
        return self._fh is not None

    def outputframe(self, frame, keyframe=True, timestamp=None, packet=None, audio=False):
        if audio or not frame:
            return
        with self._lock:
            try:
                now = time.monotonic()
                if keyframe and (self._fh is None or now - self._opened >= self._seg_s):
                    # bez pliku (brak miejsca, błąd) ponawiaj najwyżej co 30 s — bez zalewu logów
                    if self._fh is not None or now - self._checked >= 30:
                        self._rotate(now)
                if self._fh is not None:
                    self._fh.write(frame)
            except Exception as exc:
                log.error("Film: błąd zapisu (%s) — spróbuję w następnym kawałku", exc)
                self._close()
                self._checked = time.monotonic()

    def _rotate(self, now: float) -> None:
        self._close()
        self._checked = now
        os.makedirs(self._dir, exist_ok=True)
        if free_gb(self._dir) < self._min_free:
            if not self.full:
                log.warning("Film wstrzymany: mniej niż %.1f GB wolnego (dziennik lotu działa dalej)",
                            self._min_free)
            self.full = True
            return
        if self.full:
            log.info("Film: znowu jest miejsce — nagrywam")
        self.full = False
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path, n = os.path.join(self._dir, f"rec_{ts}.h264"), 1
        while os.path.exists(path):     # bez internetu zegar po restarcie może się cofnąć
            path = os.path.join(self._dir, f"rec_{ts}_{n}.h264")
            n += 1
        self._fh = open(path, "wb", buffering=1 << 20)
        self._opened = now
        self._checked = -1e9
        self.path = path
        log.info("Film → %s", path)

    def _close(self) -> None:
        if self._fh is None:
            return
        try:
            self._fh.flush()
            os.fsync(self._fh.fileno())
            self._fh.close()
        except (OSError, ValueError):
            pass
        self._fh = None

    def stop(self):
        super().stop()
        with self._lock:
            self._close()


class CameraModule:
    def __init__(self, record_dir: str, record_w: int = 1920, record_h: int = 1080,
                 record_fps: int = 25, bitrate: int = 4_000_000,
                 segment_s: int = 600, min_free_gb: float = 1.0):
        self._record_dir = record_dir
        self._segment_s = segment_s
        self._min_free_gb = min_free_gb
        self._out: SegmentOutput | None = None
        self._bitrate = bitrate
        self._recording = False
        self._cam = None

        if not _PICAM2:
            return

        try:
            os.makedirs(record_dir, exist_ok=True)
            cam = Picamera2()
            cfg = cam.create_video_configuration(
                # YUV420 idzie do kodera bez konwersji kolorów — mniej CPU niż RGB
                main={"size": (record_w, record_h), "format": "YUV420"},
                # mały podgląd RGB tylko do zdjęć wysyłanych przez LoRa
                lores={"size": (640, 360), "format": "RGB888"},
                controls={"FrameRate": record_fps},
            )
            cam.configure(cfg)
            cam.start()
        except Exception as exc:
            log.error("Camera init failed: %s — camera disabled", exc)
            return
        self._cam = cam
        log.info("Camera ready (record_dir=%s video=%dx%d@%d)",
                 record_dir, record_w, record_h, record_fps)

    @property
    def available(self) -> bool:
        return self._cam is not None

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def video_file(self) -> str | None:
        """Plik, do którego teraz idzie film (None = nie nagrywa albo brak miejsca)."""
        out = self._out
        return out.path if out is not None and out.writing else None

    def start_recording(self) -> bool:
        if not self._cam or self._recording:
            return False
        try:        # klatka kluczowa co 2 s — tak często można ciąć film na kawałki
            enc = H264Encoder(self._bitrate, repeat=True, iperiod=50)
        except TypeError:
            enc = H264Encoder(self._bitrate)
        self._out = SegmentOutput(self._record_dir, self._segment_s, self._min_free_gb)
        self._cam.start_recording(enc, self._out)
        self._recording = True
        log.info("Recording: kawałki po %d s, bitrate=%.1f Mbps", self._segment_s, self._bitrate / 1e6)
        return True

    def stop_recording(self) -> None:
        if not self._cam or not self._recording:
            return
        self._cam.stop_recording()
        self._recording = False
        log.info("Recording stopped")

    def _grab(self):
        """Klatka z małego strumienia jako obraz PIL."""
        arr = self._cam.capture_array("lores")
        # "RGB888" w picamera2 leży w pamięci jako BGR — odwróć kanały
        return _PilImage.fromarray(arr[..., 2::-1].copy())

    def snapshot_jpeg(self, quality: int = 70) -> bytes | None:
        """Klatka 640x360 do podglądu po sieci."""
        if not self._cam or not _PIL:
            return None
        try:
            buf = io.BytesIO()
            self._grab().save(buf, format="JPEG", quality=quality)
            return buf.getvalue()
        except Exception as exc:
            log.warning("Preview failed: %s", exc)
            return None

    def capture_photo(self, width: int, height: int, max_bytes: int) -> bytes | None:
        """Zdjęcie WebP w najlepszej jakości, jaka mieści się w max_bytes."""
        if not self._cam or not _PIL:
            return None
        try:
            img = self._grab()
            if img.size != (width, height):
                img = img.resize((width, height), _PilImage.LANCZOS)
            lo, hi, best = 5, 92, None
            while lo <= hi:                         # szukanie połówkowe jakości
                q = (lo + hi) // 2
                buf = io.BytesIO()
                img.save(buf, format="WEBP", quality=q, method=4)
                if buf.tell() <= max_bytes:
                    best, lo = (q, buf.getvalue()), q + 1
                else:
                    hi = q - 1
            if best is None:
                log.error("Photo: nie mieści się w %d B", max_bytes)
                return None
        except Exception as exc:
            log.error("Photo capture failed: %s", exc)
            return None
        log.info("Photo: %dx%d q=%d %d B", width, height, best[0], len(best[1]))
        return best[1]

    def set_flight(self, on: bool) -> None:
        """Lot: ostrość na nieskończoność. Na ziemi: autofokus."""
        if not self._cam:
            return
        try:
            from libcamera import controls
            if on:
                self._cam.set_controls({"AfMode": controls.AfModeEnum.Manual, "LensPosition": 0.0})
            else:
                self._cam.set_controls({"AfMode": controls.AfModeEnum.Continuous})
            log.info("Ostrość: %s", "nieskończoność" if on else "autofokus")
        except Exception as exc:        # kamera bez autofokusa
            log.warning("Ostrości nie da się ustawić: %s", exc)

    def disk_usage(self, path: str = "/") -> tuple[float, float]:
        """Returns (used_gb, free_gb) for the filesystem containing `path`."""
        try:
            st = shutil.disk_usage(path)
            used_gb = (st.total - st.free) / 1e9
            free_gb = st.free / 1e9
            return round(used_gb, 2), round(free_gb, 2)
        except Exception:
            return 0.0, 0.0

    def close(self) -> None:
        if not self._cam:
            return
        if self._recording:
            self.stop_recording()
        self._cam.stop()
        self._cam.close()
        log.info("Camera closed")
