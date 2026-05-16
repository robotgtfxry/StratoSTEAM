import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import select, desc
from database import init_db, SessionLocal
from models import TelemetryRecord, WaypointRecord
from routers import telemetry, ws, hf, commands, rpi_power, exec_cmd, camera
from routers import waypoints as waypoints_router

log = logging.getLogger("waypoint_task")

WAYPOINT_INTERVAL_S = 300   # 5 minut


async def _waypoint_task():
    """Co 5 minut pobiera ostatni rekord telemetrii i zapisuje waypoint."""
    await asyncio.sleep(10)   # krótkie opóźnienie startowe
    while True:
        try:
            async with SessionLocal() as db:
                result = await db.execute(
                    select(TelemetryRecord)
                    .order_by(desc(TelemetryRecord.id))
                    .limit(1)
                )
                rec = result.scalar_one_or_none()
                if rec and rec.lat is not None and rec.lon is not None:
                    wp = WaypointRecord(
                        ts=rec.ts,
                        lat=rec.lat,
                        lon=rec.lon,
                        alt=rec.alt,
                        bme_temp=rec.bme_temp,
                        bme_pres=rec.bme_pres,
                        voltage=rec.voltage,
                        rssi=rec.rssi,
                        seq=rec.seq,
                    )
                    db.add(wp)
                    await db.commit()
                    log.info(
                        "Waypoint saved: lat=%.5f lon=%.5f alt=%.0fm seq=%d",
                        rec.lat, rec.lon, rec.alt or 0, rec.seq,
                    )
        except Exception as e:
            log.warning("Waypoint task error: %s", e)
        await asyncio.sleep(WAYPOINT_INTERVAL_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    task = asyncio.create_task(_waypoint_task())
    yield
    task.cancel()


app = FastAPI(title="StratoSTEAM Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(telemetry.router, prefix="/api")
app.include_router(ws.router)
app.include_router(hf.router)
app.include_router(commands.router)
app.include_router(rpi_power.router)
app.include_router(exec_cmd.router)
app.include_router(camera.router)
app.include_router(waypoints_router.router, prefix="/api")
