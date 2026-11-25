"""
Faza misji (start, wznoszenie, opadanie, lądowanie) liczona na stacji naziemnej.
  POST /api/mission  — rpi-ground wrzuca bieżący stan (co kilka sekund)
  GET  /api/mission  — Flutter odczytuje

Czasy są względne (sekundy od startu / od odbioru), więc zegary stacji, serwera
i telefonu nie muszą się zgadzać.
"""
import time
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from config import settings

router = APIRouter(prefix="/api/mission", tags=["mission"])


def _verify_key(x_api_key: str = Header(...)):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad API key")


class MissionIn(BaseModel):
    phase: str = Field(max_length=40)
    elapsed: float | None = None        # sekundy od startu (T+)
    alt: float | None = None
    vs: float | None = None             # m/s
    max_alt: float | None = None
    src: str | None = Field(default=None, max_length=10)    # źródło wysokości
    auto: bool = False                  # automatyczne zdjęcia włączone
    tcpu: float | None = None           # temperatura procesora RPi balonu
    rx_age: float | None = None         # ile sekund temu stacja odebrała pakiet
    events: list[tuple[float, str]] = Field(default=[], max_length=30)   # (T+ w s, opis)


_state: dict | None = None
_received = 0.0


@router.post("", status_code=status.HTTP_200_OK)
async def update_mission(body: MissionIn, _: None = Depends(_verify_key)):
    global _state, _received
    _state = body.model_dump()
    _received = time.monotonic()
    return {"updated": True}


@router.get("")
async def get_mission():
    if _state is None:
        return {"mission": None}
    age = time.monotonic() - _received
    out = dict(_state, age=round(age, 1))
    for k in ("elapsed", "rx_age"):
        if out[k] is not None:
            out[k] = round(out[k] + age, 1)
    return {"mission": out}
