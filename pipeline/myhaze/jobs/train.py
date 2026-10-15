"""Weekly: refresh history, backtest, train the final models, store them and write the public report."""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone

from ..config import MYT, REPO_ROOT, load_settings
from ..features import build_rows, by_day_without, static_sources
from ..http import make_client
from ..model.backtest import render_markdown, run_backtest
from ..model.quantile import fit, to_text
from ..store import open_store
from .backfill import BACKFILLS, HISTORY_START
from .load_daily import refresh_archive_daily

REPORT_DIR = REPO_ROOT / "docs" / "backtest"


def refresh_inputs(client, store, settings, today: date) -> None:
    refresh_archive_daily(store, today)
    for what, table in (("weather", "weather_daily"), ("cams", "cams_daily")):
        last = store.max_day(table)
        start = max(HISTORY_START, (last or HISTORY_START) - timedelta(days=2))
        BACKFILLS[what](client, store, settings, start, today)


def collect_rows(store, today: date):
    start = HISTORY_START
    cells = store.fire_cells(start - timedelta(days=4), today)
    cells_by_day = by_day_without(cells, static_sources(cells))
    daily_pm = store.daily_pm25(start - timedelta(days=3), today)
    weather = store.weather_daily(start, today + timedelta(days=2))
    cams_daily = store.cams_daily(start - timedelta(days=7), today)
    issue_days = [start + timedelta(days=i) for i in range((today - start).days)]
    return (build_rows(store.stations(), daily_pm, cells_by_day, weather, issue_days, cams_daily=cams_daily),
            cams_daily, daily_pm)


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    if not settings.db_url:
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 2
    today = datetime.now(MYT).date()
    store = open_store(settings.db_url)
    if store is None:
        return 1
    try:
        with make_client() as client:
            refresh_inputs(client, store, settings, today)
        rows, cams_daily, daily_pm = collect_rows(store, today)
        try:
            report = run_backtest(rows, cams_daily, daily_pm)
        except ValueError as exc:
            print(f"cannot train yet: {exc}", file=sys.stderr)
            return 1
        boosters = {lead: to_text(fit([r for r in rows if r.lead == lead], report["leads"][str(lead)]["rounds"]))
                    for lead in (1, 2)}
        methods = {lead: report["leads"][str(lead)]["method"] for lead in (1, 2)}
        version = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
        report["version"] = version
        store.save_model_version(version, methods, report, boosters)
        store.prune_models()
    finally:
        store.close()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "latest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (REPORT_DIR / "latest.md").write_text(render_markdown(report), encoding="utf-8")
    for lead, entry in report["leads"].items():
        m = entry["model"]
        print(f"lead {lead}: ships {entry['method']}; model band {m['band_accuracy']}, "
              f"unhealthy caught {m['pod_unhealthy']}, target met {entry['meets_target']}")
    print("version:", version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
