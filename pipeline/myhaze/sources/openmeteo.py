"""Open-Meteo air-quality API: CAMS PM2.5 forecasts at station points."""
from __future__ import annotations

import math
import time
from datetime import date, datetime, timedelta, timezone

import httpx

from ..http import FetchError, get_json
from ..rows import CamsForecast, HourlyWeather, Station

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


FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
# Everything the archive of past forecasts can supply; mixing height is live-forecast only.
WEATHER_VARS = ("precipitation", "wind_speed_10m", "wind_speed_120m", "wind_direction_120m", "relative_humidity_2m")


def _items(payload, points: list[Station]) -> list:
    items = payload if isinstance(payload, list) else [payload]
    if len(items) != len(points):
        raise FetchError(f"Open-Meteo returned {len(items)} locations for {len(points)} points")
    return items


def parse_weather(payload, points: list[Station], suffix: str = "") -> list[HourlyWeather]:
    weather = []
    for point, item in zip(points, _items(payload, points)):
        hourly = item.get("hourly") if isinstance(item, dict) else None
        if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
            continue
        try:
            times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in hourly["time"]]
        except (TypeError, ValueError):
            continue

        def column(name: str) -> list[float | None]:
            values = hourly.get(name + suffix)
            if isinstance(values, list) and len(values) == len(times):
                return [_value(v) for v in values]
            return [None] * len(times)

        weather.append(HourlyWeather(point.station_id, times, column("precipitation"), column("boundary_layer_height"),
                                     column("wind_speed_10m"), column("wind_speed_120m"),
                                     column("wind_direction_120m"), column("relative_humidity_2m")))
    return weather


def _batched_weather(client: httpx.Client, url: str, points: list[Station], params: dict, label: str,
                     suffix: str = "", deadline: float | None = None) -> list[HourlyWeather]:
    weather = []
    for start in range(0, len(points), BATCH):
        if deadline is not None and time.monotonic() > deadline:
            raise FetchError(f"{label} ran out of time after {start} of {len(points)} points")
        chunk = points[start:start + BATCH]
        payload = get_json(client, url, params=dict(params, latitude=",".join(f"{p.lat:.4f}" for p in chunk),
                                                     longitude=",".join(f"{p.lon:.4f}" for p in chunk)), label=label)
        weather.extend(parse_weather(payload, chunk, suffix))
    return weather


def fetch_weather_forecast(client: httpx.Client, points: list[Station], days: int = 4) -> list[HourlyWeather]:
    # 4 days from today's UTC midnight: late in the MYT evening the 48 h path still reaches the day after tomorrow.
    hourly = ",".join(WEATHER_VARS + ("boundary_layer_height",))
    return _batched_weather(client, FORECAST_URL, points,
                            {"hourly": hourly, "forecast_days": days, "past_days": 1, "timezone": "GMT"},
                            "Open-Meteo forecast")


def fetch_wind_grid(client: httpx.Client, points: list[Station], days: int = 3,
                    deadline: float | None = None) -> list[HourlyWeather]:
    """Wind about 120 m up at grid points, for the map's flowing-wind layer (3 days from today's UTC midnight).

    `deadline` (time.monotonic()) stops a slow fetch so it can never hold up the forecast job."""
    return _batched_weather(client, FORECAST_URL, points,
                            {"hourly": "wind_speed_120m,wind_direction_120m", "forecast_days": days, "timezone": "GMT"},
                            "Open-Meteo wind grid", deadline=deadline)


def fetch_previous_runs(client: httpx.Client, points: list[Station], start: date, end: date,
                        lead: int) -> list[HourlyWeather]:
    suffix = f"_previous_day{lead}"
    # One day earlier than `start` so the first Malaysia day (which begins 16:00 UTC the day before) is complete.
    return _batched_weather(client, PREVIOUS_RUNS_URL, points,
                            {"hourly": ",".join(v + suffix for v in WEATHER_VARS),
                             "start_date": (start - timedelta(days=1)).isoformat(), "end_date": end.isoformat(),
                             "timezone": "GMT"}, "Open-Meteo previous runs", suffix)


def fetch_cams_hourly_history(client: httpx.Client, stations: list[Station], start: date,
                              end: date) -> dict[str, dict[datetime, float]]:
    series: dict[str, dict[datetime, float]] = {}
    for first in range(0, len(stations), BATCH):
        chunk = stations[first:first + BATCH]
        payload = get_json(client, AQ_URL, params={
            "latitude": ",".join(f"{s.lat:.4f}" for s in chunk), "longitude": ",".join(f"{s.lon:.4f}" for s in chunk),
            "hourly": "pm2_5", "start_date": (start - timedelta(days=1)).isoformat(), "end_date": end.isoformat(),
            "timezone": "GMT"}, label="Open-Meteo air-quality history")
        for forecast in parse_cams(payload, chunk, datetime.min.replace(tzinfo=timezone.utc)):
            series[forecast.station_id] = {forecast.first_valid + timedelta(hours=i): v
                                           for i, v in enumerate(forecast.pm25) if v is not None}
    return series
