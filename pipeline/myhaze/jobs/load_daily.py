"""Load the owner's aqicn daily CSV exports and our archive's daily means into daily_pm25."""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..config import MYT, REPO_ROOT, load_settings
from ..convert import aqicn_aqi_to_ugm3
from ..daily import daily_means
from ..sources.aqicn_csv import parse_daily_csv
from ..store import open_store

HISTORY_START = date(2026, 7, 1)
CSV_DIR = REPO_ROOT / "data" / "raw" / "aqicn_daily"


def load_csv_dir(store, directory: Path = CSV_DIR, since: date = HISTORY_START) -> dict:
    known = {s.station_id for s in store.stations()}
    rows, files, unknown, unreadable = [], 0, [], []
    for path in sorted(Path(directory).glob("*.csv")):
        station_id = path.stem.strip().upper()
        if station_id not in known:
            unknown.append(path.name)
            continue
        try:
            series = parse_daily_csv(path.read_text(encoding="utf-8-sig"))
        except ValueError:
            unreadable.append(path.name)
            continue
        files += 1
        rows += [(station_id, day, round(aqicn_aqi_to_ugm3(aqi), 2), "aqicn_csv") for day, aqi in series if day >= since]
    return {"files": files, "rows": store.upsert_daily_pm25(rows), "unknown_files": unknown, "unreadable": unreadable}


def refresh_archive_daily(store, today: date) -> dict:
    """Daily means of our own hourly aqicn archive for complete Malaysia days before `today`."""
    since = datetime.combine(today - timedelta(days=10), datetime.min.time(), MYT).astimezone(timezone.utc)
    rows = []
    for station_id, series in store.hourly_series("aqicn", "pm25_aqi", since).items():
        conc = {hour: aqicn_aqi_to_ugm3(aqi) for hour, aqi in series.items()}
        rows += [(station_id, day, round(value, 2), "archive") for day, value in daily_means(conc).items() if day < today]
    return {"archive_rows": store.upsert_daily_pm25(rows)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load daily PM2.5 history into daily_pm25.")
    parser.add_argument("--dir", type=Path, default=CSV_DIR)
    args = parser.parse_args(argv)
    settings = load_settings()
    if not settings.db_url:
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 2
    store = open_store(settings.db_url)
    if store is None:
        return 1
    try:
        print(load_csv_dir(store, args.dir))
        print(refresh_archive_daily(store, datetime.now(MYT).date()))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
