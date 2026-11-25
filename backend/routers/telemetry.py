from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional

from database import get_db
from models import TelemetryRecord
from schemas import TelemetryIn, TelemetryOut
from config import settings
from routers.ws import broadcast

router = APIRouter(tags=["telemetry"])


def _verify_key(x_api_key: str = Header(...)):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad API key")


@router.post("/telemetry", status_code=status.HTTP_201_CREATED, response_model=TelemetryOut)
async def ingest(
    body: TelemetryIn,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(_verify_key),
):
    record = TelemetryRecord(
        seq=body.seq,
        ts=body.ts,
        rssi=body.rssi,
        snr=body.snr,
        lat=body.gps.lat,
        lon=body.gps.lon,
        alt=body.gps.alt,
        speed_kmh=body.gps.spd,
        heading=body.gps.hdg,
        satellites=body.gps.sat,
        gps_fix=body.gps.fix,
        bme_temp=body.bme.temperature_c,
        bme_hum=body.bme.humidity_pct,
        bme_pres=body.bme.pressure_hpa,
        ms_temp=body.ms.temperature_c,
        ms_pres=body.ms.pressure_hpa,
        ms_alt=body.ms.altitude_m,
        roll=body.imu.roll_deg,
        pitch=body.imu.pitch_deg,
        yaw=body.imu.yaw_deg,
        voltage=body.pwr.voltage_v,
        current_ma=body.pwr.current_ma,
        power_mw=body.pwr.power_mw,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    out = TelemetryOut.model_validate(record)
    await broadcast(out.model_dump(mode="json"))
    return out


@router.get("/telemetry", response_model=list[TelemetryOut])
async def list_telemetry(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TelemetryRecord).order_by(desc(TelemetryRecord.id)).limit(limit)
    )
    return result.scalars().all()


@router.get("/telemetry/latest", response_model=Optional[TelemetryOut])
async def latest(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TelemetryRecord).order_by(desc(TelemetryRecord.id)).limit(1)
    )
    return result.scalar_one_or_none()
