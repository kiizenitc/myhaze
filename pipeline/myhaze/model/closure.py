"""Would MOE's published haze rules close schools? An indicator only: MOE makes the decision.

Rules as reported on 8 Oct 2026: close when the official API exceeds 180, or when it stays above
150 on three consecutive days. The two rules share days, so the indicator is max(rule A, rule B).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from ..config import MYT

SUN_TO_THU_STATES = {"Kedah", "Kelantan", "Terengganu"}
CLOSE_ABOVE = 180.0
STREAK_ABOVE = 150.0
STREAK_DAYS = 3
DECISION_HOUR = 7  # from 07:00 MYT the next school day is tomorrow at the earliest
Z80 = 1.2816
MIN_DAY_HOURS = 18  # too little of the school day inside the 48 h forecast: say nothing


def is_school_day(day: date, state: str) -> bool:
    weekday = day.weekday()  # Monday = 0 … Sunday = 6
    return weekday in (6, 0, 1, 2, 3) if state in SUN_TO_THU_STATES else weekday <= 4


def next_school_day(now: datetime, state: str) -> date:
    local = now.astimezone(MYT)
    day = local.date()
    if local.hour >= DECISION_HOUR or not is_school_day(day, state):
        day += timedelta(days=1)
        while not is_school_day(day, state):
            day += timedelta(days=1)
    return day


def p_above(p50: float, low: float | None, high: float | None, threshold: float) -> float:
    if low is None or high is None or low <= 0 or high <= low:
        return 1.0 if p50 > threshold else 0.0
    sigma = (math.log(high) - math.log(low)) / (2 * Z80)
    z = (math.log(threshold) - math.log(max(p50, 1e-6))) / sigma
    return 0.5 * math.erfc(z / math.sqrt(2))


def _day_max_probability(times, official, day: date, threshold: float) -> float | None:
    low, mid, high = official
    hours = [i for i, t in enumerate(times) if t.astimezone(MYT).date() == day and mid[i] is not None]
    if len(hours) < MIN_DAY_HOURS:
        return None
    i = max(hours, key=lambda j: mid[j])
    return p_above(mid[i], low[i], high[i], threshold)


def closure_indicator(state: str, now: datetime, times: list[datetime], official: tuple[list, list, list],
                      observed_daily_max: dict[date, float]) -> dict:
    day = next_school_day(now, state)
    rule_a = _day_max_probability(times, official, day, CLOSE_ABOVE)
    if rule_a is None:
        return {"school_day": day.isoformat(), "probability": None, "rule": None}
    today = now.astimezone(MYT).date()
    rule_b = 1.0
    for d in (day - timedelta(days=k) for k in range(STREAK_DAYS)):
        seen = 1.0 if (observed_daily_max.get(d) or 0.0) > STREAK_ABOVE else 0.0
        if d < today:
            rule_b *= seen
        else:
            forecast = _day_max_probability(times, official, d, STREAK_ABOVE)
            rule_b *= max(seen, forecast or 0.0)
    rule = "api_above_180" if rule_a >= rule_b else "three_days_above_150"
    return {"school_day": day.isoformat(), "probability": round(max(rule_a, rule_b), 2), "rule": rule}
