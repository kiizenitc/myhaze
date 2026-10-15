"""Daily: score archived forecasts against what was then observed (hourly Real Feel bands)."""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from ..config import MYT, load_settings
from ..convert import aqicn_aqi_to_ugm3, band, ugm3_to_api
from ..metrics import OK_BANDS
from ..store import Store


def score_runs(runs, observed: dict[str, dict[datetime, float]]) -> list[tuple[date, str, int, int, int, int]]:
    totals: dict[tuple[date, str], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for _run_at, station_id, first_valid, pm25 in runs:
        seen = observed.get(station_id, {})
        for h, value in enumerate(pm25):
            if h == 0 or value is None:
                continue
            t = first_valid + timedelta(hours=h)
            actual = seen.get(t)
            if actual is None:
                continue
            predicted_band, actual_band = band(ugm3_to_api(value)), band(ugm3_to_api(actual))
            entry = totals[(t.astimezone(MYT).date(), "1-24h" if h <= 24 else "25-48h")]
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
    now = datetime.now(timezone.utc)
    store = Store.connect(settings.db_url)
    try:
        runs = store.forecast_runs(now - timedelta(days=3))
        observed = {sid: {t: aqicn_aqi_to_ugm3(v) for t, v in series.items()}
                    for sid, series in store.hourly_series("aqicn", "pm25_aqi", now - timedelta(days=6)).items()}
        rows = score_runs(runs, observed)
        store.upsert_verification(rows)
        print(f"verified {len(runs)} runs into {len(rows)} day/horizon rows")
        print(store.verification_summary())
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
