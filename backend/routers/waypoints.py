"""
Waypoints — snapshots co 5 minut (pozycja + parametry) do wyświetlenia na mapie.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Optional
import datetime

from database import get_db
from models import WaypointRecord

router = APIRouter(tags=["waypoints"])


class WaypointOut(BaseModel):
    id:          int
    ts:          int
    recorded_at: datetime.datetime
    lat:         Optional[float]
    lon:         Optional[float]
    alt:         Optional[float]
    bme_temp:    float
    bme_pres:    float
    voltage:     float
    rssi:        int
    seq:         int

    class Config:
        from_attributes = True


@router.get("/waypoints", response_model=list[WaypointOut])
async def list_waypoints(
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WaypointRecord).order_by(desc(WaypointRecord.id)).limit(limit)
    )
    return result.scalars().all()
