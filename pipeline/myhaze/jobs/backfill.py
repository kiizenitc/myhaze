"""One-off and incremental history backfills: python -m myhaze.jobs.backfill <what> [--start] [--end]."""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

from ..config import MYT, load_settings
from ..http import make_client
from ..sources import firms
from ..store import Store

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


BACKFILLS = {"fires": backfill_fires}


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
