"""Daily weather summaries on Malaysia days, and the points whose rain matters for the fire regions."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from .config import MYT
from .rows import HourlyWeather, Station

WET_MM = 0.5
# Rain here suppresses the peat fires that send smoke to Malaysia.
RAIN_POINTS = (
    Station("R:riau", "Riau", "Indonesia", 0.5, 101.5),
    Station("R:jambi", "Jambi", "Indonesia", -1.6, 103.6),
    Station("R:south_sumatra", "South Sumatra", "Indonesia", -3.3, 104.9),
    Station("R:west_kalimantan", "West Kalimantan", "Indonesia", -0.1, 110.0),
    Station("R:central_kalimantan", "Central Kalimantan", "Indonesia", -1.7, 113.4),
    Station("R:south_kalimantan", "South Kalimantan", "Indonesia", -3.0, 115.3),
)


@dataclass(frozen=True)
class WeatherDay:
    precip_mm: float | None
    wet_hours: int | None
    wind10_kmh: float | None
    wind120_kmh: float | None
    wind120_from_deg: float | None
    rh_mean: float | None


def _mean(values) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 2) if present else None


def circular_mean_deg(directions, weights) -> float | None:
    x = y = 0.0
    seen = False
    for direction, weight in zip(directions, weights):
        if direction is None:
            continue
        w = 1.0 if weight is None else max(weight, 0.0)
        x += w * math.sin(math.radians(direction))
        y += w * math.cos(math.radians(direction))
        seen = True
    if not seen or (abs(x) < 1e-9 and abs(y) < 1e-9):
        return None
    return round((math.degrees(math.atan2(x, y)) + 360.0) % 360.0, 2)


def daily_weather(hw: HourlyWeather, min_hours: int = 18) -> dict[date, WeatherDay]:
    by_day: dict[date, list[int]] = defaultdict(list)
    for i, t in enumerate(hw.times):
        by_day[t.astimezone(MYT).date()].append(i)
    days = {}
    for day, idx in by_day.items():
        if len(idx) < min_hours:
            continue
        rain = [hw.precip[i] for i in idx if hw.precip[i] is not None]
        days[day] = WeatherDay(
            precip_mm=round(sum(rain), 2) if rain else None,
            wet_hours=sum(1 for v in rain if v >= WET_MM) if rain else None,
            wind10_kmh=_mean(hw.wind10[i] for i in idx),
            wind120_kmh=_mean(hw.wind120[i] for i in idx),
            wind120_from_deg=circular_mean_deg([hw.wind120_from[i] for i in idx], [hw.wind120[i] for i in idx]),
            rh_mean=_mean(hw.rh[i] for i in idx),
        )
    return days
