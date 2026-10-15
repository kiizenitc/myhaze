"""Daily and trailing means of hourly series, on Malaysia calendar days."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from .config import MYT


def daily_means(series: dict[datetime, float], min_hours: int = 18) -> dict[date, float]:
    by_day: dict[date, list[float]] = defaultdict(list)
    for hour, value in series.items():
        by_day[hour.astimezone(MYT).date()].append(value)
    return {day: sum(v) / len(v) for day, v in by_day.items() if len(v) >= min_hours}


def trailing_mean(series: dict[datetime, float], end_hour: datetime, hours: int = 24,
                  min_hours: int = 18) -> float | None:
    values = [series[t] for t in (end_hour - timedelta(hours=k) for k in range(hours)) if t in series]
    return sum(values) / len(values) if len(values) >= min_hours else None
