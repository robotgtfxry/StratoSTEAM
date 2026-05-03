"""
HF transmitter control.
Flutter sends commands here → rpi-ground polls and executes them.
"""
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
from typing import Literal
from config import settings

router = APIRouter(prefix="/api/hf", tags=["hf"])

# In-memory state — simple and sufficient
_command: dict = {"action": "stop", "freq_hz": 7_100_000}
_hw_status: dict = {"active": False, "freq_hz": 0}


def _verify_key(x_api_key: str = Header(...)):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad API key")


class HfCommandIn(BaseModel):
    action: Literal["start", "stop", "set_freq"]
    freq_hz: int = 7_100_000


class HfStatusIn(BaseModel):
    active: bool
    freq_hz: int


class HfStateOut(BaseModel):
    command: dict
    hw_status: dict


# Flutter → backend: send a command
@router.post("/control", response_model=HfStateOut)
async def control(body: HfCommandIn, _: None = Depends(_verify_key)):
    global _command
    _command = body.model_dump()
    return HfStateOut(command=_command, hw_status=_hw_status)


# rpi-ground → backend: fetch pending command
@router.get("/command")
async def get_command(_: None = Depends(_verify_key)):
    return _command


# rpi-ground → backend: report actual hardware status
@router.post("/status")
async def report_status(body: HfStatusIn, _: None = Depends(_verify_key)):
    global _hw_status
    _hw_status = body.model_dump()
    return {"ok": True}


# Flutter → backend: read current state (command + hw status)
@router.get("/state", response_model=HfStateOut)
async def get_state():
    return HfStateOut(command=_command, hw_status=_hw_status)
