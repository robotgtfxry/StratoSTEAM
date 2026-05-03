"""
Uplink command queue: Flutter enqueues, rpi-ground dequeues and sends via LoRa.
"""
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
from config import settings

router = APIRouter(prefix="/api/commands", tags=["commands"])

# Single pending command — ground picks it up on the next telemetry cycle
_pending: dict | None = None


def _verify_key(x_api_key: str = Header(...)):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad API key")


class CommandIn(BaseModel):
    buzzer: bool = False
    led_r: int = 0
    led_g: int = 0
    led_b: int = 0


class CommandOut(BaseModel):
    has_command: bool
    command: dict | None = None


@router.post("/send", status_code=status.HTTP_202_ACCEPTED)
async def enqueue(body: CommandIn, _: None = Depends(_verify_key)):
    global _pending
    _pending = body.model_dump()
    return {"queued": True, "command": _pending}


@router.get("/pending", response_model=CommandOut)
async def dequeue(_: None = Depends(_verify_key)):
    global _pending
    if _pending is None:
        return CommandOut(has_command=False)
    cmd = _pending
    _pending = None   # consumed — ground will send it once
    return CommandOut(has_command=True, command=cmd)


@router.get("/current", response_model=CommandOut)
async def peek():
    """Flutter can read current queued command without consuming it."""
    return CommandOut(has_command=_pending is not None, command=_pending)
