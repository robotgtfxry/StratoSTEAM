"""
ESP32-CAM status routes.
  POST /api/espcam/status   — rpi-ground wrzuca status (z pola "ec" w telemetrii)
  GET  /api/espcam/status   — Flutter odczytuje status wszystkich kamer
"""
import time
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from config import settings

router = APIRouter(prefix="/api/espcam", tags=["espcam"])


def _verify_key(x_api_key: str = Header(...)):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad API key")


# ── In-memory state ───────────────────────────────────────────────────────────
# Lista 4 statusów kamer, aktualizowana przez rpi-ground przy każdym pakiecie telemetrii
_cam_statuses: list[dict] = [
    {"cam": i, "ok": False, "recording": False, "frames": 0,
     "free_mb": 0, "reachable": False, "updated_at": None}
    for i in range(4)
]


class EspCamStatusIn(BaseModel):
    # ec: [[ok, recording, frames, free_mb], ...] — kompaktowy format z pakietu LoRa
    ec: list[list]


@router.post("/status", status_code=status.HTTP_200_OK)
async def update_status(body: EspCamStatusIn, _: None = Depends(_verify_key)):
    global _cam_statuses
    now = time.time()
    for i, cam_data in enumerate(body.ec[:4]):
        if len(cam_data) >= 4:
            _cam_statuses[i] = {
                "cam":       i,
                "ok":        bool(cam_data[0]),
                "recording": bool(cam_data[1]),
                "frames":    int(cam_data[2]),
                "free_mb":   int(cam_data[3]),
                "reachable": bool(cam_data[0]) or bool(cam_data[1]),
                "updated_at": now,
            }
    return {"updated": len(body.ec)}


@router.get("/status")
async def get_status():
    return {"cameras": _cam_statuses, "ts": time.time()}
