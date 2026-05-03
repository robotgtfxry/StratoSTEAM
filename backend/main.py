from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import init_db
from routers import telemetry, ws, hf, commands, rpi_power, exec_cmd


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


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
