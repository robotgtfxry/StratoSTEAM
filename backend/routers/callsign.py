"""
Znak wywoławczy sondy ustawiany w aplikacji.
  POST /api/callsign  — Flutter: {"cs": "SP8DEV-1"}
  GET  /api/callsign  — rpi-ground i Flutter: {"desired": "..."}
Znak, którym sonda faktycznie nadaje, jest w /api/mission (pole "cs" z beaconu).
"""
import json
import os
import re
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from config import settings

router = APIRouter(prefix="/api/callsign", tags=["callsign"])
_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "callsign.json")
_RE = re.compile(r"^[A-Z0-9/]{3,10}(-[0-9]{1,2})?$")      # musi zgadzać się z esp32 validCallsign()


def _verify_key(x_api_key: str = Header(...)):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad API key")


def _load() -> str | None:
    try:
        with open(_PATH, encoding="utf-8") as f:
            return json.load(f).get("desired")
    except (OSError, ValueError):
        return None


class CallsignIn(BaseModel):
    cs: str


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def set_callsign(body: CallsignIn, _: None = Depends(_verify_key)):
    cs = body.cs.strip().upper()
    if not _RE.match(cs):
        raise HTTPException(status_code=422, detail="Znak: litery, cyfry i /, opcjonalnie -SSID (np. SP8DEV-1)")
    with open(_PATH + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"desired": cs}, f)
    os.replace(_PATH + ".tmp", _PATH)
    return {"desired": cs}


@router.get("")
async def get_callsign(_: None = Depends(_verify_key)):
    return {"desired": _load()}
