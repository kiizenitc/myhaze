"""Pick the aqicn US-AQI table and DOE's PM2.5 table that best reproduce DOE's published API.

DOE's API for PM2.5 is its PM2.5 table applied to the 24-hour running mean concentration; aqicn
relays the same monitors' hourly PM2.5 as a US AQI. Each (aqicn table, DOE table) pair is scored
by mean absolute error against DOE's own numbers.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .convert import MY_TABLES, US_TABLES, conc_from_index, index_from_conc


def calibrate(aqicn_hourly: dict[str, dict[datetime, float]], doe_api: dict[str, dict[datetime, float]],
              min_hours: int = 20, min_pairs: int = 200) -> dict:
    scores: dict[str, float] = {}
    best: tuple[float, str, str, int] | None = None
    for us_name, us_table in US_TABLES.items():
        pairs = []
        for station_id, apis in doe_api.items():
            conc = {t: conc_from_index(v, us_table) for t, v in aqicn_hourly.get(station_id, {}).items()}
            for hour, api in apis.items():
                window = [conc.get(hour - timedelta(hours=k)) for k in range(24)]
                values = [v for v in window if v is not None]
                if len(values) >= min_hours:
                    pairs.append((sum(values) / len(values), api))
        if len(pairs) < min_pairs:
            continue
        for my_name, my_table in MY_TABLES.items():
            mae = sum(abs(index_from_conc(mean24, my_table) - api) for mean24, api in pairs) / len(pairs)
            scores[f"{us_name}+{my_name}"] = round(mae, 2)
            if best is None or mae < best[0]:
                best = (mae, us_name, my_name, len(pairs))
    if best is None:
        raise ValueError(f"not enough overlapping hours yet (need {min_pairs} station-hours with {min_hours}+ "
                         "hours of aqicn data in the preceding day)")
    mae, us_name, my_name, n = best
    return {"aqicn_table": us_name, "my_table": my_name, "mae": round(mae, 2), "n": n, "scores": scores}
