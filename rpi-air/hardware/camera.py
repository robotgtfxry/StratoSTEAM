"""
Camera module: continuous H.264 recording to disk + on-demand photo capture.
Photos are compressed to WebP small enough for one LoRa burst (see esp32/src/main.cpp).
"""
import io
import logging
import os
import shutil
from datetime import datetime

log = logging.getLogger(__name__)

try:
    from picamera2 import Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FileOutput
    _PICAM2 = True
except ImportError:
    _PICAM2 = False
    log.warning("picamera2 not available — camera disabled")

try:
    from PIL import Image as _PilImage
    _PIL = True
except ImportError:
    _PIL = False


class CameraModule:
    def __init__(self, record_dir: str, record_w: int = 1920, record_h: int = 1080,
                 record_fps: int = 25, bitrate: int = 4_000_000):
        self._record_dir = record_dir
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

    def start_recording(self) -> str | None:
        if not self._cam or self._recording:
            return None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self._record_dir, f"rec_{ts}.h264")
        n = 1
        while os.path.exists(path):     # bez internetu zegar po restarcie może się cofnąć
            path = os.path.join(self._record_dir, f"rec_{ts}_{n}.h264")
            n += 1
        self._cam.start_recording(H264Encoder(self._bitrate), FileOutput(path))
        self._recording = True
        log.info("Recording → %s  bitrate=%.1f Mbps", path, self._bitrate / 1e6)
        return path

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
