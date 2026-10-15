"""Archive DOE official API, aqicn hourly readings and CAMS forecasts into Supabase.

Runs every 15 minutes. Every step is idempotent and skips work already stored,
so repeated or overlapping runs are harmless.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ..config import load_settings
from ..http import FetchError, make_client
from ..sources import aqicn, doe, openmeteo
from ..store import Store

DOE_PAUSE_S = 0.5
DOE_UP_TO_DATE_SHARE = 0.9
# Time budgets keep a hanging source from running the job past its workflow timeout.
DOE_BUDGET_S = 150.0
AQICN_BUDGET_S = 300.0
AQICN_MAPPING_MIN_SHARE = 0.8


@dataclass
class RunResult:
    status: str
    details: dict = field(default_factory=dict)


def _hour(now: datetime) -> datetime:
    return now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _safe_message(exc: Exception) -> str:
    """FetchError text is vetted (no URLs or keys); any other message might echo a secret, so keep only its type."""
    return str(exc) if isinstance(exc, FetchError) else type(exc).__name__


def _failure(exc: Exception) -> dict:
    return {"status": "failed", "errors": [_safe_message(exc)]}


def sync_stations(client, store, settings, now_utc: datetime) -> dict:
    if store.stations() and now_utc.minute >= 15:
        return {"status": "skipped", "reason": "synced at the start of the hour"}
    stations = doe.fetch_stations(client)
    if not stations:
        raise FetchError("DOE mapcaqm returned no stations")
    detail: dict = {"stations": len(stations)}
    mapping = None
    if settings.aqicn_token:
        try:
            mapping = aqicn.match_stations(stations, aqicn.fetch_bounds(client, settings.aqicn_token))
            detail["aqicn_matched"] = len(mapping)
        except FetchError as exc:
            detail["aqicn_error"] = str(exc)
        previous = len(store.aqicn_uids())
        if mapping is not None and previous and len(mapping) < AQICN_MAPPING_MIN_SHARE * previous:
            detail["aqicn_mapping_rejected"] = f"{len(mapping)} matches, {previous} before"
            mapping = None
    store.upsert_stations(stations, mapping)
    return {"status": "ok", **detail}


def archive_doe(client, store, now_utc: datetime, backfill_days: int = 0, *,
                budget_s: float = DOE_BUDGET_S, clock=time.monotonic) -> dict:
    active = len(store.stations())
    if not backfill_days and active and store.count_obs_at("doe", _hour(now_utc)) >= DOE_UP_TO_DATE_SHARE * active:
        return {"status": "skipped", "reason": "hour already stored"}
    rows: dict = {}
    errors: list[str] = []
    started = clock()
    for state_id in doe.fetch_state_ids(client):
        if clock() - started > budget_s:
            errors.append("DOE time budget exceeded; remaining states wait for the next run")
            break
        for days_back in range(backfill_days + 1):
            try:
                for obs in doe.fetch_hourly(client, state_id, now_utc - timedelta(days=days_back)):
                    rows[(obs.station_id, obs.hour)] = obs
            except Exception as exc:
                errors.append(f"state {state_id}: {_safe_message(exc)}")
            time.sleep(DOE_PAUSE_S)
    if not rows and not errors:
        errors.append("DOE returned no readings")
    written, unknown = store.upsert_obs(list(rows.values())) if rows else (0, 0)
    status = "ok" if not errors else ("partial" if written else "failed")
    return {"status": status, "written": written, "unknown_station": unknown,
            "errors": errors[:5], "error_count": len(errors)}


def archive_aqicn(client, store, settings, now_utc: datetime, *,
                  budget_s: float = AQICN_BUDGET_S, clock=time.monotonic) -> dict:
    if not settings.aqicn_token:
        return {"status": "skipped", "reason": "AQICN_TOKEN not set"}
    uids = store.aqicn_uids()
    if not uids:
        return {"status": "skipped", "reason": "no stations matched to aqicn yet"}
    hour = _hour(now_utc)
    latest = store.latest_hours("aqicn")
    todo = {station_id: uid for station_id, uid in uids.items() if latest.get(station_id) != hour}
    if not todo:
        return {"status": "skipped", "reason": "hour already stored"}
    rows, errors = [], []
    started = clock()
    for station_id, uid in sorted(todo.items()):
        if clock() - started > budget_s:
            errors.append("aqicn time budget exceeded; remaining stations wait for the next run")
            break
        try:
            obs = aqicn.fetch_feed(client, settings.aqicn_token, uid, station_id)
        except FetchError as exc:
            errors.append(f"{station_id}: {exc}")
            continue
        if obs is not None:
            rows.append(obs)
    written, _unknown = store.upsert_obs(rows) if rows else (0, 0)
    status = "ok" if not errors else ("partial" if len(errors) < len(todo) else "failed")
    return {"status": status, "written": written, "requested": len(todo),
            "errors": errors[:5], "error_count": len(errors)}


def archive_cams(client, store, now_utc: datetime) -> dict:
    slot = openmeteo.six_hour_slot(now_utc)
    if store.cams_slot_done(slot):
        return {"status": "skipped", "reason": "slot already stored"}
    written = store.upsert_cams(openmeteo.fetch_cams(client, store.stations(), slot))
    return {"status": "ok" if written else "failed", "written": written, "slot": slot.isoformat()}


def run(now_utc: datetime, settings, client, store, *, doe_backfill_days: int = 0) -> RunResult:
    started = datetime.now(timezone.utc)
    # aqicn first: its hourly readings can never be fetched again, while DOE keeps about 7 days.
    steps = {
        "stations": lambda: sync_stations(client, store, settings, now_utc),
        "aqicn": lambda: archive_aqicn(client, store, settings, now_utc),
        "doe": lambda: archive_doe(client, store, now_utc, doe_backfill_days),
        "cams": lambda: archive_cams(client, store, now_utc),
    }
    details: dict[str, dict] = {}
    for name, step in steps.items():
        try:
            details[name] = step()
        except Exception as exc:
            details[name] = _failure(exc)
    if details["doe"]["status"] == "failed" and details["aqicn"]["status"] == "failed":
        status = "failed"
    elif any(d["status"] in ("failed", "partial") for d in details.values()):
        status = "partial"
    else:
        status = "ok"
    try:
        store.log_run("archive", started, datetime.now(timezone.utc), status, details)
    except Exception as exc:
        details["run_log"] = _failure(exc)
        status = "failed"
    return RunResult(status, details)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive DOE, aqicn and CAMS data into Supabase.")
    parser.add_argument("--doe-backfill-days", type=int, default=0,
                        help="also fetch DOE's previous N days (DOE keeps about 7)")
    args = parser.parse_args(argv)
    settings = load_settings()
    if not settings.db_url:
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 2
    store = Store.connect(settings.db_url)
    try:
        with make_client() as client:
            result = run(datetime.now(timezone.utc), settings, client, store,
                         doe_backfill_days=args.doe_backfill_days)
    finally:
        store.close()
    for name, detail in result.details.items():
        extras = ", ".join(f"{k}={v}" for k, v in detail.items() if k != "status")
        print(f"{name:9s} {detail['status']:8s} {extras}")
    print("run:", result.status)
    return 1 if result.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
