"""
ESP32-CAM status routes (jedna kamera na balonie).
  POST /api/espcam/status   — rpi-ground wrzuca status (pole "ec" z telemetrii)
  GET  /api/espcam/status   — Flutter odczytuje status kamery
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
# Status kamery, aktualizowany przez rpi-ground przy każdym pakiecie telemetrii
_cam_status: dict = {
    "ok": False, "recording": False, "frames": 0,
    "free_mb": 0, "reachable": False, "updated_at": None,
}


class EspCamStatusIn(BaseModel):
    # ec: [ok, recording, frames, free_mb] — kompaktowy format z pakietu LoRa
    ec: list


@router.post("/status", status_code=status.HTTP_200_OK)
async def update_status(body: EspCamStatusIn, _: None = Depends(_verify_key)):
    global _cam_status
    if len(body.ec) < 4:
        raise HTTPException(status_code=422, detail="ec must be [ok, rec, frames, free_mb]")
    ok, rec, frames, free_mb = body.ec[:4]
    _cam_status = {
        "ok":        bool(ok),
        "recording": bool(rec),
        "frames":    int(frames),
        "free_mb":   int(free_mb),
        "reachable": bool(ok) or bool(rec),
        "updated_at": time.time(),
    }
    return {"updated": True}


@router.get("/status")
async def get_status():
    return {"camera": _cam_status, "ts": time.time()}
