"""Plain records passed between sources, the store and jobs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Station:
    station_id: str
    name: str
    state: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Obs:
    """One hourly observation from one source. `hour` is timezone-aware UTC, on the hour."""
    station_id: str
    hour: datetime
    source: str
    api: int | None = None
    param_symbol: str | None = None
    pm25_aqi: int | None = None
    pm10_aqi: int | None = None
    o3_aqi: float | None = None
    no2_aqi: float | None = None
    so2_aqi: float | None = None
    co_aqi: float | None = None
    temp_c: float | None = None
    rh: float | None = None
    wind: float | None = None
    pressure: float | None = None


@dataclass(frozen=True)
class CamsForecast:
    """CAMS hourly PM2.5 (µg/m³) at a station, as fetched in one 6-hour slot."""
    station_id: str
    issued_slot: datetime
    first_valid: datetime
    pm25: list[float | None]
