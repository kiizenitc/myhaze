"""The simple forecasts the trained model must beat."""
from __future__ import annotations

from datetime import date, timedelta

from .features import FeatureRow


def persistence(row: FeatureRow) -> float | None:
    """Tomorrow looks like today."""
    return row.x.get("pm_d0")


def cams_corrected(station_id: str, issue_day: date, target_day: date, cams_daily: dict[tuple[str, date], float],
                   daily_pm: dict[tuple[str, date], float], window: int = 7, min_days: int = 3) -> float | None:
    """CAMS's daily mean for the target day, scaled by how far CAMS was off at this station over the last week."""
    target = cams_daily.get((station_id, target_day))
    if target is None:
        return None
    observed = modelled = 0.0
    days = 0
    for k in range(window):
        day = issue_day - timedelta(days=k)
        obs, cams = daily_pm.get((station_id, day)), cams_daily.get((station_id, day))
        if obs is not None and cams is not None and cams > 0:
            observed += obs
            modelled += cams
            days += 1
    if days < min_days or modelled <= 0:
        return None
    return target * observed / modelled
