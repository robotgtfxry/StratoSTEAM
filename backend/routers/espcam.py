"""
ESP-CAM power control routes.
  POST /api/espcam/power          — Flutter sets power state for one/all cameras
  GET  /api/espcam/power/pending  — rpi-ground polls for pending command
  GET  /api/espcam/power/state    — Flutter reads current known state
"""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from config import settings

router = APIRouter(prefix="/api/espcam", tags=["espcam"])


def _verify_key(x_api_key: str = Header(...)):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad API key")


# ── In-memory state ───────────────────────────────────────────────────────────

_pending: dict | None = None          # {"cam": int, "on": bool}
_state: list[bool] = [False] * 4      # last known power state per camera


class PowerIn(BaseModel):
    cam: int   # 0-3 for single, -1 for all
    on: bool


@router.post("/power", status_code=status.HTTP_202_ACCEPTED)
async def set_power(body: PowerIn, _: None = Depends(_verify_key)):
    global _pending
    if body.cam not in (-1, 0, 1, 2, 3):
        raise HTTPException(status_code=422, detail="cam must be -1..3")
    _pending = {"cam": body.cam, "on": body.on}
    # Optimistically update state
    idxs = range(4) if body.cam == -1 else [body.cam]
    for i in idxs:
        _state[i] = body.on
    return {"queued": True, "cam": body.cam, "on": body.on}


@router.get("/power/pending")
async def power_pending(_: None = Depends(_verify_key)):
    global _pending
    if _pending is None:
        return {"pending": False, "cam": 0, "on": False}
    val = _pending
    _pending = None
    return {"pending": True, "cam": val["cam"], "on": val["on"]}


@router.get("/power/state")
async def power_state():
    return {"state": _state}
