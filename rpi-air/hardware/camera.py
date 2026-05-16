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
                 photo_quality: int = 25):
        self._record_dir = record_dir
        self._photo_w = photo_w
        self._photo_h = photo_h
        self._photo_quality = photo_quality
        self._recording = False
        self._cam = None
        self._photo_id = 0

        if not _PICAM2:
            return

        os.makedirs(record_dir, exist_ok=True)
        self._cam = Picamera2()
        cfg = self._cam.create_video_configuration(
            main={"size": (1280, 720), "format": "RGB888"},
        )
        self._cam.configure(cfg)
        self._cam.start()
        log.info("Camera ready (record_dir=%s photo=%dx%d q=%d)",
                 record_dir, photo_w, photo_h, photo_quality)

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
        self._cam.start_recording(H264Encoder(), FileOutput(path))
        self._recording = True
        log.info("Recording → %s", path)
        return path

    def stop_recording(self) -> None:
        if not self._cam or not self._recording:
            return
        self._cam.stop_recording()
        self._recording = False
        log.info("Recording stopped")

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
            arr = self._cam.capture_array("main")   # RGB888, 1280x720
            if _PIL:
                img = _PilImage.fromarray(arr)
                img = img.resize((self._photo_w, self._photo_h), _PilImage.LANCZOS)
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
