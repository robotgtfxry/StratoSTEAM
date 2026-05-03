"""
Remote exec over LoRa.
Flutter → POST /api/exec/send → rpi-ground polls → LoRa → rpi-air executes
rpi-air → LoRa result → rpi-ground → POST /api/exec/result → Flutter polls
"""
import time
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
from config import settings

router = APIRouter(prefix="/api/exec", tags=["exec"])

_pending_cmd: dict | None = None   # waiting to be picked up by rpi-ground
_last_result: dict | None = None   # last result from rpi-air


def _verify_key(x_api_key: str = Header(...)):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


class ExecCmd(BaseModel):
    sh: str


class ExecResult(BaseModel):
    rc: int
    out: str
    err: str


# Flutter → queue a command
@router.post("/send", status_code=status.HTTP_202_ACCEPTED)
async def send_cmd(body: ExecCmd, _: None = Depends(_verify_key)):
    global _pending_cmd, _last_result
    _pending_cmd = {"sh": body.sh, "ts": int(time.time())}
    _last_result = None   # clear previous result
    return {"queued": True, "sh": body.sh}


# rpi-ground → fetch and consume pending command
@router.get("/pending")
async def get_pending(_: None = Depends(_verify_key)):
    global _pending_cmd
    if _pending_cmd is None:
        return {"has_command": False}
    cmd = _pending_cmd
    _pending_cmd = None
    return {"has_command": True, **cmd}


# rpi-ground → post result received from rpi-air
@router.post("/result")
async def post_result(body: ExecResult, _: None = Depends(_verify_key)):
    global _last_result
    _last_result = {"rc": body.rc, "out": body.out, "err": body.err,
                    "ts": int(time.time())}
    return {"ok": True}


# Flutter → poll for result
@router.get("/result")
async def get_result():
    if _last_result is None:
        return {"ready": False}
    return {"ready": True, **_last_result}
