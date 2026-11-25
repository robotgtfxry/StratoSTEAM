from pydantic import BaseModel
from typing import Optional
import datetime


class GpsPayload(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    alt: Optional[float] = None
    spd: Optional[float] = None
    hdg: Optional[float] = None
    sat: int = 0
    fix: bool = False


class BmePayload(BaseModel):
    temperature_c: float = 0.0
    humidity_pct: float = 0.0
    pressure_hpa: float = 0.0


class MsPayload(BaseModel):
    temperature_c: float = 0.0
    pressure_hpa: float = 0.0
    altitude_m: float = 0.0


class ImuPayload(BaseModel):
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 0.0


class PwrPayload(BaseModel):
    voltage_v: float = 0.0
    current_ma: float = 0.0
    power_mw: float = 0.0


class TelemetryIn(BaseModel):
    seq: int
    ts: int
    gps: GpsPayload = GpsPayload()
    bme: BmePayload = BmePayload()
    ms:  MsPayload  = MsPayload()
    imu: ImuPayload = ImuPayload()
    pwr: PwrPayload = PwrPayload()
    rssi: int = 0
    snr:  float = 0.0


class TelemetryOut(BaseModel):
    id: int
    seq: int
    ts: int
    received_at: datetime.datetime
    rssi: int
    snr: float
    lat: Optional[float]
    lon: Optional[float]
    alt: Optional[float]
    speed_kmh: Optional[float]
    satellites: int
    gps_fix: bool
    bme_temp: float
    bme_hum: float
    bme_pres: float
    ms_temp: float
    ms_pres: float
    ms_alt: float
    roll: float
    pitch: float
    yaw: float
    voltage: float
    current_ma: float
    power_mw: float

    class Config:
        from_attributes = True
