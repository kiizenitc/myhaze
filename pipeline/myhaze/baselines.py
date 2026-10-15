"""The simple forecasts the trained model must beat."""
from __future__ import annotations

from datetime import date

from .features import FeatureRow, cams_ratio


def persistence(row: FeatureRow) -> float | None:
    """Tomorrow looks like today."""
    return row.x.get("pm_d0")


def cams_corrected(station_id: str, issue_day: date, target_day: date, cams_daily: dict[tuple[str, date], float],
                   daily_pm: dict[tuple[str, date], float], window: int = 7, min_days: int = 3) -> float | None:
    """CAMS's daily mean for the target day, scaled by how far CAMS was off at this station over the last week."""
    target = cams_daily.get((station_id, target_day))
    ratio = cams_ratio(station_id, issue_day, cams_daily, daily_pm, window, min_days)
    return None if target is None or ratio is None else target * ratio
