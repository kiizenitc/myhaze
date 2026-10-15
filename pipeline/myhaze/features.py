"""One feature builder for training and live forecasting, so the backtest cannot use hindsight.

Issue day D (a Malaysia date) predicts the daily-mean PM2.5 of target day D + lead from:
PM2.5 up to and including D; fire cells of the last complete UTC day before the issue (D - 1)
and three days before the issue (D - 3, for the trend); weather *forecasts* for the target day; and
CAMS's PM2.5 for the target day with this station's recent observed/CAMS ratio. (CAMS history comes from
Open-Meteo's near-real-time archive, so the backtest is somewhat flattering for it; the owner accepted this.)
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np

from .config import MYT
from .geo import region_of
from .rows import FireCell, HourlyWeather, Station
from .sources.firms import GRID_DEG
from .weather import RAIN_POINTS, WeatherDay, daily_weather

REGION_GROUP = {"Perlis": 0, "Kedah": 0, "Pulau Pinang": 0, "Perak": 0, "Selangor": 0, "WP Kuala Lumpur": 0,
                "WP Putrajaya": 0, "Negeri Sembilan": 0, "Melaka": 0, "Kelantan": 1, "Terengganu": 1, "Pahang": 1,
                "Johor": 2, "Sarawak": 3, "Sabah": 4, "WP Labuan": 4}
FIRE_REGIONS = ("sumatra", "kalimantan", "peninsular", "my_borneo")
FEATURES = ("pm_d0", "pm_d1", "pm_d2", "pm_trend", "region_pm_d0", "upwind_fire", "fire_sumatra", "fire_kalimantan",
            "fire_peninsular", "fire_my_borneo", "fire_trend", "rain_mm", "wet_hours", "rain_fire_regions",
            "wind10_kmh", "wind120_kmh", "wind_from_sin", "wind_from_cos", "rh_mean", "lat", "lon", "region_group",
            "cams_target", "cams_ratio")
MONOTONE = {"upwind_fire": 1, "rain_mm": -1, "rain_fire_regions": -1}
UPWIND_EFOLD_KM = 500.0
EARTH_KM = 6371.0


@dataclass
class FeatureRow:
    station_id: str
    issue_day: date
    lead: int
    target_day: date
    x: dict[str, float | None]
    y: float | None
    upwind_by_region: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class CellArrays:
    lat: np.ndarray  # radians, cell centres
    lon: np.ndarray
    frp: np.ndarray
    region: np.ndarray


def cell_arrays(cells: list[FireCell]) -> CellArrays | None:
    if not cells:
        return None
    lat = np.array([c.lat_bin + GRID_DEG / 2 for c in cells])
    lon = np.array([c.lon_bin + GRID_DEG / 2 for c in cells])
    return CellArrays(np.radians(lat), np.radians(lon), np.array([c.frp_sum for c in cells], dtype=float),
                      np.array([region_of(la, lo) for la, lo in zip(lat, lon)]))


def region_totals(arrays: CellArrays | None) -> dict[str, float]:
    if arrays is None:
        return dict.fromkeys(FIRE_REGIONS, 0.0)
    return {r: float(arrays.frp[arrays.region == r].sum()) for r in FIRE_REGIONS}


def upwind_by_region(station: Station, arrays: CellArrays | None, wind_from_deg: float | None) -> dict[str, float]:
    """Fire power weighted by distance (e-folding 500 km) and by how squarely it lies upwind."""
    regions = dict.fromkeys(FIRE_REGIONS + ("other",), 0.0)
    if arrays is None or wind_from_deg is None:
        return regions
    lat1, lon1 = math.radians(station.lat), math.radians(station.lon)
    dl = arrays.lon - lon1
    a = np.sin((arrays.lat - lat1) / 2) ** 2 + math.cos(lat1) * np.cos(arrays.lat) * np.sin(dl / 2) ** 2
    km = 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    bearing = np.degrees(np.arctan2(np.sin(dl) * np.cos(arrays.lat),
                                    math.cos(lat1) * np.sin(arrays.lat) - math.sin(lat1) * np.cos(arrays.lat) * np.cos(dl)))
    align = np.clip(np.cos(np.radians(bearing - wind_from_deg)), 0.0, None)
    weight = arrays.frp * np.exp(-km / UPWIND_EFOLD_KM) * align
    return {r: float(weight[arrays.region == r].sum()) for r in regions}


def _region_means(stations: list[Station], daily_pm: dict, day: date) -> dict[int, float]:
    groups: dict[int, list[float]] = defaultdict(list)
    for s in stations:
        value = daily_pm.get((s.station_id, day))
        if value is not None:
            groups[REGION_GROUP.get(s.state, 0)].append(value)
    return {g: sum(v) / len(v) for g, v in groups.items()}


def cams_ratio(station_id: str, issue_day: date, cams_daily: dict[tuple[str, date], float],
               daily_pm: dict[tuple[str, date], float], window: int = 7, min_days: int = 3) -> float | None:
    """How far CAMS was off at this station over the week ending on the issue day (observed / CAMS)."""
    observed = modelled = 0.0
    days = 0
    for k in range(window):
        day = issue_day - timedelta(days=k)
        obs, cams = daily_pm.get((station_id, day)), cams_daily.get((station_id, day))
        if obs is not None and cams is not None and cams > 0:
            observed += obs
            modelled += cams
            days += 1
    return observed / modelled if days >= min_days and modelled > 0 else None


def _log_ratio(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else math.log1p(a) - math.log1p(b)


def build_rows(stations: list[Station], daily_pm: dict[tuple[str, date], float],
               cells_by_day: dict[date, list[FireCell]], weather: dict[tuple[str, date, int], WeatherDay],
               issue_days: list[date], leads: tuple[int, ...] = (1, 2),
               cams_daily: dict[tuple[str, date], float] | None = None) -> list[FeatureRow]:
    cams_daily = cams_daily or {}
    arrays_cache: dict[date, CellArrays | None] = {}

    def arrays_for(day: date) -> CellArrays | None:
        if day not in arrays_cache:
            arrays_cache[day] = cell_arrays(cells_by_day.get(day, []))
        return arrays_cache[day]

    rows = []
    for issue in issue_days:
        fires = arrays_for(issue - timedelta(days=1))
        totals, totals_before = region_totals(fires), region_totals(arrays_for(issue - timedelta(days=3)))
        region_pm = _region_means(stations, daily_pm, issue)
        for lead in leads:
            target = issue + timedelta(days=lead)
            rain = [w.precip_mm for p in RAIN_POINTS
                    if (w := weather.get((p.station_id, target, lead))) is not None and w.precip_mm is not None]
            rain_fire = sum(rain) / len(rain) if rain else None
            for s in stations:
                pm0, pm1, pm2 = (daily_pm.get((s.station_id, issue - timedelta(days=k))) for k in range(3))
                wd = weather.get((s.station_id, target, lead))
                wind_from = wd.wind120_from_deg if wd else None
                upwind = upwind_by_region(s, fires, wind_from)
                x = {
                    "pm_d0": pm0, "pm_d1": pm1, "pm_d2": pm2, "pm_trend": _log_ratio(pm0, pm2),
                    "region_pm_d0": region_pm.get(REGION_GROUP.get(s.state, 0)),
                    "upwind_fire": math.log1p(sum(upwind.values())) if wind_from is not None else None,
                    **{f"fire_{r}": math.log1p(totals[r]) for r in FIRE_REGIONS},
                    "fire_trend": _log_ratio(sum(totals.values()), sum(totals_before.values())),
                    "rain_mm": wd.precip_mm if wd else None,
                    "wet_hours": float(wd.wet_hours) if wd and wd.wet_hours is not None else None,
                    "rain_fire_regions": rain_fire,
                    "wind10_kmh": wd.wind10_kmh if wd else None,
                    "wind120_kmh": wd.wind120_kmh if wd else None,
                    "wind_from_sin": math.sin(math.radians(wind_from)) if wind_from is not None else None,
                    "wind_from_cos": math.cos(math.radians(wind_from)) if wind_from is not None else None,
                    "rh_mean": wd.rh_mean if wd else None,
                    "lat": s.lat, "lon": s.lon, "region_group": float(REGION_GROUP.get(s.state, 0)),
                    "cams_target": (math.log1p(cams_daily[(s.station_id, target)])
                                    if (s.station_id, target) in cams_daily else None),
                    "cams_ratio": cams_ratio(s.station_id, issue, cams_daily, daily_pm),
                }
                rows.append(FeatureRow(s.station_id, issue, lead, target, x, daily_pm.get((s.station_id, target)),
                                       upwind))
    return rows


def live_weather_days(latest: dict[str, HourlyWeather], issue: date,
                      leads: tuple[int, ...] = (1, 2)) -> dict[tuple[str, date, int], WeatherDay]:
    days = {}
    for station_id, hw in latest.items():
        summary = daily_weather(hw)
        for lead in leads:
            target = issue + timedelta(days=lead)
            if target in summary:
                days[(station_id, target, lead)] = summary[target]
    return days


def build_live_rows(stations: list[Station], now: datetime, pm_now: dict[str, float],
                    daily_pm: dict[tuple[str, date], float], cells_by_day: dict[date, list[FireCell]],
                    weather_latest: dict[str, HourlyWeather], leads: tuple[int, ...] = (1, 2),
                    cams_daily: dict[tuple[str, date], float] | None = None) -> list[FeatureRow]:
    issue = now.astimezone(MYT).date()
    pm = {key: value for key, value in daily_pm.items() if key[1] < issue}
    pm.update({(station_id, issue): value for station_id, value in pm_now.items()})
    return build_rows(stations, pm, cells_by_day, live_weather_days(weather_latest, issue, leads), [issue], leads,
                      cams_daily)
