from sqlalchemy import Integer, Float, Boolean, String, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from database import Base
import datetime


class TelemetryRecord(Base):
    __tablename__ = "telemetry"

    id:         Mapped[int]      = mapped_column(Integer, primary_key=True, index=True)
    seq:        Mapped[int]      = mapped_column(Integer, index=True)
    ts:         Mapped[int]      = mapped_column(Integer)              # unix timestamp from balloon
    received_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    rssi:       Mapped[int]      = mapped_column(Integer, default=0)
    snr:        Mapped[float]    = mapped_column(Float, default=0.0)

    # GPS
    lat:        Mapped[float | None] = mapped_column(Float, nullable=True)
    lon:        Mapped[float | None] = mapped_column(Float, nullable=True)
    alt:        Mapped[float | None] = mapped_column(Float, nullable=True)
    speed_kmh:  Mapped[float | None] = mapped_column(Float, nullable=True)
    heading:    Mapped[float | None] = mapped_column(Float, nullable=True)
    satellites: Mapped[int]          = mapped_column(Integer, default=0)
    gps_fix:    Mapped[bool]         = mapped_column(Boolean, default=False)

    # BME280
    bme_temp:   Mapped[float] = mapped_column(Float, default=0.0)
    bme_hum:    Mapped[float] = mapped_column(Float, default=0.0)
    bme_pres:   Mapped[float] = mapped_column(Float, default=0.0)

    # MS5611
    ms_temp:    Mapped[float] = mapped_column(Float, default=0.0)
    ms_pres:    Mapped[float] = mapped_column(Float, default=0.0)
    ms_alt:     Mapped[float] = mapped_column(Float, default=0.0)

    # BNO085
    roll:       Mapped[float] = mapped_column(Float, default=0.0)
    pitch:      Mapped[float] = mapped_column(Float, default=0.0)
    yaw:        Mapped[float] = mapped_column(Float, default=0.0)

    # INA219
    voltage:    Mapped[float] = mapped_column(Float, default=0.0)
    current_ma: Mapped[float] = mapped_column(Float, default=0.0)
    power_mw:   Mapped[float] = mapped_column(Float, default=0.0)
