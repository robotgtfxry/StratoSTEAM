"""
ESP32-CAM power control routes (jedna kamera na balonie).
  POST /api/espcam/power          — Flutter ustawia stan zasilania kamery
  GET  /api/espcam/power/pending  — rpi-ground odpytuje o oczekującą komendę
  GET  /api/espcam/power/state    — Flutter czyta ostatni znany stan
"""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from config import settings

router = APIRouter(prefix="/api/espcam", tags=["espcam"])


def _verify_key(x_api_key: str = Header(...)):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad API key")


# ── In-memory state ───────────────────────────────────────────────────────────

_pending: bool | None = None    # oczekujący stan zasilania
_state: bool = False            # ostatni znany stan kamery


class PowerIn(BaseModel):
    on: bool


@router.post("/power", status_code=status.HTTP_202_ACCEPTED)
async def set_power(body: PowerIn, _: None = Depends(_verify_key)):
    global _pending, _state
    _pending = body.on
    _state = body.on          # optymistyczna aktualizacja
    return {"queued": True, "on": body.on}


@router.get("/power/pending")
async def power_pending(_: None = Depends(_verify_key)):
    global _pending
    if _pending is None:
        return {"pending": False, "on": False}
    val = _pending
    _pending = None
    return {"pending": True, "on": val}


@router.get("/power/state")
async def power_state():
    return {"on": _state}
