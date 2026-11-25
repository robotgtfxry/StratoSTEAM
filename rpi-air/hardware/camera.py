"""
Camera module: continuous H.264 recording to disk + on-demand photo capture.
Photos are split into base64 chunks for LoRa retransmission via ESP32.
"""
import base64
import io
import logging
import os
import shutil
from datetime import datetime

log = logging.getLogger(__name__)

_CHUNK_BYTES = 140   # raw bytes per chunk → 187 base64 chars, LoRa packet ~245 bytes

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
    def __init__(self, record_dir: str, photo_w: int = 160, photo_h: int = 120,
                 photo_quality: int = 25, record_w: int = 1920, record_h: int = 1080,
                 record_fps: int = 25, bitrate: int = 4_000_000):
        self._record_dir = record_dir
        self._photo_w = photo_w
        self._photo_h = photo_h
        self._photo_quality = photo_quality
        self._bitrate = bitrate
        self._recording = False
        self._cam = None
        self._photo_id = 0

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
        log.info("Camera ready (record_dir=%s video=%dx%d@%d photo=%dx%d q=%d)",
                 record_dir, record_w, record_h, record_fps, photo_w, photo_h, photo_quality)

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

    def capture_photo_chunks(self) -> list[tuple[int, int, int, str]]:
        """
        Capture one photo, compress it, split into chunks.
        Returns list of (img_id, seq, total, base64_str).
        """
        if not self._cam:
            return []

        self._photo_id = (self._photo_id % 255) + 1
        img_id = self._photo_id

        try:
            if _PIL:
                img = self._grab().resize((self._photo_w, self._photo_h), _PilImage.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=self._photo_quality, optimize=True)
                jpeg = buf.getvalue()
            else:
                buf = io.BytesIO()
                self._cam.capture_file(buf, format="jpeg")
                jpeg = buf.getvalue()
        except Exception as exc:
            log.error("Photo capture failed: %s", exc)
            return []

        total = (len(jpeg) + _CHUNK_BYTES - 1) // _CHUNK_BYTES
        chunks = []
        for seq in range(total):
            raw = jpeg[seq * _CHUNK_BYTES:(seq + 1) * _CHUNK_BYTES]
            b64 = base64.b64encode(raw).decode("ascii")
            chunks.append((img_id, seq, total, b64))

        log.info("Photo: %d bytes → %d chunks (id=%d)", len(jpeg), total, img_id)
        return chunks

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
