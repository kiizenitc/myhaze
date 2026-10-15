"""Open-Meteo air-quality API: CAMS PM2.5 forecasts at station points."""
from __future__ import annotations

import math
from datetime import datetime, timezone

import httpx

from ..http import FetchError, get_json
from ..rows import CamsForecast, Station

AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
BATCH = 25
FORECAST_DAYS = 5


def six_hour_slot(now: datetime) -> datetime:
    utc = now.astimezone(timezone.utc)
    return utc.replace(hour=utc.hour - utc.hour % 6, minute=0, second=0, microsecond=0)


def parse_cams(payload, stations: list[Station], issued_slot: datetime) -> list[CamsForecast]:
    items = payload if isinstance(payload, list) else [payload]
    if len(items) != len(stations):
        raise FetchError(f"Open-Meteo returned {len(items)} locations for {len(stations)} stations")
    forecasts = []
    for station, item in zip(stations, items):
        hourly = item.get("hourly") if isinstance(item, dict) else None
        if not isinstance(hourly, dict):
            continue
        times, values = hourly.get("time") or [], hourly.get("pm2_5") or []
        if not isinstance(times, list) or not isinstance(values, list) or not times or len(times) != len(values):
            continue
        try:
            first_valid = datetime.fromisoformat(times[0]).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        forecasts.append(CamsForecast(station.station_id, issued_slot, first_valid, [_value(v) for v in values]))
    return forecasts


def _value(raw) -> float | None:
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def fetch_cams(client: httpx.Client, stations: list[Station], issued_slot: datetime) -> list[CamsForecast]:
    forecasts = []
    for start in range(0, len(stations), BATCH):
        chunk = stations[start:start + BATCH]
        payload = get_json(client, AQ_URL, params={
            "latitude": ",".join(f"{s.lat:.4f}" for s in chunk),
            "longitude": ",".join(f"{s.lon:.4f}" for s in chunk),
            "hourly": "pm2_5",
            "forecast_days": FORECAST_DAYS,
            "timezone": "GMT",
        }, label="Open-Meteo air-quality")
        forecasts.extend(parse_cams(payload, chunk, issued_slot))
    return forecasts
