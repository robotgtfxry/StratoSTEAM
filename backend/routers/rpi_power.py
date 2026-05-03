"""
RPi power control via ESP32-S3.
Flutter sets desired state → rpi-ground polls and sends LoRa command to ESP32.
rpi-ground also reports whether RPi is currently running (based on packet source).
"""
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
from config import settings

router = APIRouter(prefix="/api/rpi_power", tags=["rpi_power"])

_desired_on: bool | None = None   # None = no pending command
_rpi_running: bool = False        # last known state reported by rpi-ground


def _verify_key(x_api_key: str = Header(...)):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad API key")


class PowerCmd(BaseModel):
    on: bool


class PowerStatus(BaseModel):
    rpi_running: bool


class PowerStateOut(BaseModel):
    rpi_running: bool
    pending: bool
    pending_on: bool | None = None


# Flutter → set desired power state
@router.post("/set", status_code=status.HTTP_202_ACCEPTED)
async def set_power(body: PowerCmd, _: None = Depends(_verify_key)):
    global _desired_on
    _desired_on = body.on
    return {"queued": True, "on": _desired_on}


# rpi-ground → fetch pending command (consumes it)
@router.get("/pending")
async def get_pending(_: None = Depends(_verify_key)):
    global _desired_on
    if _desired_on is None:
        return {"has_command": False}
    on = _desired_on
    _desired_on = None
    return {"has_command": True, "on": on}


# rpi-ground → report actual RPi running state
@router.post("/status")
async def report_status(body: PowerStatus, _: None = Depends(_verify_key)):
    global _rpi_running
    _rpi_running = body.rpi_running
    return {"ok": True}


# Flutter → read current state
@router.get("/state", response_model=PowerStateOut)
async def get_state():
    return PowerStateOut(
        rpi_running=_rpi_running,
        pending=_desired_on is not None,
        pending_on=_desired_on,
    )
