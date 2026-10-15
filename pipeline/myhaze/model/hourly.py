"""Turn daily forecast levels into a 48-hour path of hourly PM2.5 (µg/m³).

The path starts at the live reading and relaxes to the model (e-folding 6 h). It is shaped by
forecast mixing height (smoke concentrates under a shallow early-morning layer) and lowered by rain.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from ..config import MYT
from ..convert import ugm3_to_api
from ..rows import HourlyWeather

HORIZON_H = 48
ANCHOR_EFOLD_H = 6.0
BLH_EXPONENT = 0.3
FACTOR_RANGE = (0.6, 1.8)
TRAPPED_FACTOR = 1.3
WASHOUT = 0.85
WASHOUT_MM = 1.0
ANCHOR_FLOOR = 1.0  # µg/m³: a zero or glitched reading must not wipe out the path
ANCHOR_PULL = (0.25, 4.0)  # the live reading moves the path at most 4x either way
OFFICIAL_HANDOVER_H = 24


@dataclass
class HourlyPath:
    times: list[datetime]
    p10: list[float]
    p50: list[float]
    p90: list[float]
    trapped: list[bool]


def _noon(day: date) -> datetime:
    return datetime.combine(day, time(12), MYT).astimezone(timezone.utc)


def _level(t: datetime, levels: dict[date, tuple[float, float, float]]) -> tuple[float, float, float]:
    """Log-linear between the noon points of consecutive days; flat beyond the first and last."""
    points = [(_noon(d), levels[d]) for d in sorted(levels)]
    if t <= points[0][0]:
        return points[0][1]
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t <= t1:
            w = (t - t0) / (t1 - t0)
            return tuple(math.exp((1 - w) * math.log(max(a, 0.1)) + w * math.log(max(b, 0.1))) for a, b in zip(v0, v1))
    return points[-1][1]


def diurnal_factors(weather: HourlyWeather | None) -> dict[datetime, float]:
    if weather is None:
        return {}
    by_day: dict[date, list[tuple[datetime, float]]] = defaultdict(list)
    for t, blh in zip(weather.times, weather.blh):
        if blh is not None and blh > 0:
            by_day[t.astimezone(MYT).date()].append((t, blh))
    factors = {}
    for values in by_day.values():
        if len(values) < 18:
            continue
        mean_blh = sum(b for _, b in values) / len(values)
        raw = {t: min(max((b / mean_blh) ** -BLH_EXPONENT, FACTOR_RANGE[0]), FACTOR_RANGE[1]) for t, b in values}
        norm = sum(raw.values()) / len(raw)
        factors.update({t: f / norm for t, f in raw.items()})
    return factors


def build_path(now_hour: datetime, levels: dict[date, tuple[float, float, float]],
               weather: HourlyWeather | None, anchor: float | None) -> HourlyPath:
    times = [now_hour + timedelta(hours=h) for h in range(HORIZON_H)]
    factors = diurnal_factors(weather)
    rain = dict(zip(weather.times, weather.precip)) if weather else {}
    path = HourlyPath(times, [], [], [], [])
    first = None
    for h, t in enumerate(times):
        low, mid, high = _level(t, levels)
        mid = max(mid, 0.1)
        factor = factors.get(t, 1.0)
        model = mid * factor * (WASHOUT if (rain.get(t) or 0.0) >= WASHOUT_MM else 1.0)
        if first is None:
            first = model
        if anchor is not None and first > 0:
            decay = math.exp(-h / ANCHOR_EFOLD_H)
            pull = min(max(max(anchor, ANCHOR_FLOOR) / first, ANCHOR_PULL[0]), ANCHOR_PULL[1])
            value, spread = model * pull ** decay, 1.0 - decay
        else:
            value, spread = model, 1.0
        path.p50.append(round(value, 2))
        path.p10.append(round(value * (low / mid) ** spread, 2))
        path.p90.append(round(value * (high / mid) ** spread, 2))
        path.trapped.append(factor >= TRAPPED_FACTOR)
    return path


def official_api_path(path: HourlyPath, observed: dict[datetime, float], fallback: float | None,
                      official_now: float | None = None) -> tuple[list, list, list]:
    """DOE's API is a 24-hour running mean: combine observed past hours with forecast future hours.

    DOE's own figure for this hour wins over our reconstruction; the gap fades out over a day."""
    start = path.times[0]
    result = []
    for series in (path.p10, path.p50, path.p90):
        values = []
        for t in path.times:
            window = []
            for back in range(24):
                u = t - timedelta(hours=back)
                if u < start or (u == start and u in observed):
                    v = observed.get(u, fallback)
                else:
                    v = series[int((u - start).total_seconds() // 3600)]
                if v is not None:
                    window.append(v)
            values.append(ugm3_to_api(sum(window) / len(window)) if window else None)
        result.append(values)
    offset = 0.0
    if official_now is not None and result[1][0] is not None:
        offset = official_now - result[1][0]
    for values in result:
        for h, v in enumerate(values):
            if v is not None:
                fade = max(0.0, 1.0 - h / OFFICIAL_HANDOVER_H)
                values[h] = round(max(v + offset * fade, 0.0), 1)
    return tuple(result)
