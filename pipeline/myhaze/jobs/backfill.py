"""One-off and incremental history backfills: python -m myhaze.jobs.backfill <what> [--start] [--end]."""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

from ..config import MYT, load_settings
from ..daily import daily_means
from ..http import make_client
from ..sources import firms, openmeteo
from ..store import Store
from ..weather import RAIN_POINTS, daily_weather

HISTORY_START = date(2026, 7, 1)


def backfill_fires(client, store, settings, start: date, end: date) -> dict:
    if not settings.firms_key:
        raise SystemExit("FIRMS_MAP_KEY is not set")
    availability = firms.fetch_availability(client, settings.firms_key)
    written = 0
    day = start
    while day <= end:  # 30-day slices keep memory small and progress visible
        last = min(day + timedelta(days=29), end)
        written += store.upsert_fire_cells(firms.fetch_cells(client, settings.firms_key, day, last, availability))
        print(f"fires {day}..{last}: {written} cells so far", flush=True)
        day = last + timedelta(days=1)
    return {"cells": written}


def backfill_weather(client, store, settings, start: date, end: date) -> dict:
    points = store.stations() + list(RAIN_POINTS)
    rows = []
    for lead in (1, 2):
        for hw in openmeteo.fetch_previous_runs(client, points, start, end, lead):
            rows += [(hw.station_id, day, lead, wd) for day, wd in daily_weather(hw).items() if start <= day <= end]
    return {"weather_rows": store.upsert_weather_daily(rows)}


def backfill_cams(client, store, settings, start: date, end: date) -> dict:
    series = openmeteo.fetch_cams_hourly_history(client, store.stations(), start, end)
    rows = [(sid, day, round(value, 2)) for sid, hourly in series.items()
            for day, value in daily_means(hourly).items() if start <= day <= end]
    return {"cams_rows": store.upsert_cams_daily(rows)}


BACKFILLS = {"fires": backfill_fires, "weather": backfill_weather, "cams": backfill_cams}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill history into Supabase.")
    parser.add_argument("what", choices=sorted(BACKFILLS))
    parser.add_argument("--start", type=date.fromisoformat, default=HISTORY_START)
    parser.add_argument("--end", type=date.fromisoformat, default=None)
    args = parser.parse_args(argv)
    settings = load_settings()
    if not settings.db_url:
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 2
    end = args.end or datetime.now(MYT).date()
    store = Store.connect(settings.db_url)
    try:
        with make_client() as client:
            print(BACKFILLS[args.what](client, store, settings, args.start, end))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
