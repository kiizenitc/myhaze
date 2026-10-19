"""Daily: score archived forecasts against what was then observed (hourly Real Feel bands)."""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from ..config import MYT, load_settings
from ..convert import aqicn_aqi_to_ugm3, band, ugm3_to_real_feel
from ..metrics import OK_BANDS
from ..store import open_store


def score_runs(runs, observed: dict[str, dict[datetime, float]],
               only_day: date | None = None) -> list[tuple[date, str, int, int, int, int]]:
    """Hits per (MYT day, horizon). With only_day, hours on other days are ignored: a half-observed day scores nothing."""
    totals: dict[tuple[date, str], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for _run_at, station_id, first_valid, pm25 in runs:
        seen = observed.get(station_id, {})
        for h, value in enumerate(pm25):
            if h == 0 or value is None:
                continue
            t = first_valid + timedelta(hours=h)
            day = t.astimezone(MYT).date()
            if only_day is not None and day != only_day:
                continue
            actual = seen.get(t)
            if actual is None:
                continue
            predicted_band, actual_band = band(ugm3_to_real_feel(value)), band(ugm3_to_real_feel(actual))
            entry = totals[(day, "1-24h" if h <= 24 else "25-48h")]
            entry[0] += 1
            entry[1] += predicted_band == actual_band
            if actual_band not in OK_BANDS:
                entry[2] += 1
                entry[3] += predicted_band not in OK_BANDS
    return [(day, horizon, *values) for (day, horizon), values in sorted(totals.items())]


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    if not settings.db_url:
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 2
    # Score yesterday (MYT) only: it is complete, and every run that could forecast it started within 48 h before it.
    day = datetime.now(MYT).date() - timedelta(days=1)
    day_start = datetime.combine(day, time(0), MYT).astimezone(timezone.utc)
    store = open_store(settings.db_url)
    if store is None:
        return 1
    try:
        runs = store.forecast_runs(day_start - timedelta(hours=48))
        observed = {sid: {t: aqicn_aqi_to_ugm3(v) for t, v in series.items()}
                    for sid, series in store.hourly_series("aqicn", "pm25_aqi", day_start - timedelta(days=1)).items()}
        rows = score_runs(runs, observed, only_day=day)
        store.upsert_verification(rows)
        print(f"verified {len(runs)} runs into {len(rows)} day/horizon rows")
        print(store.verification_summary())
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
