"""Hourly: build every station's 48-hour forecast and write the website's JSON files (site-data/)."""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..baselines import cams_corrected
from ..config import MYT, REPO_ROOT, load_settings
from ..convert import aqicn_aqi_to_ugm3, api_to_ugm3
from ..daily import daily_means, trailing_mean
from ..features import FeatureRow, build_live_rows
from ..http import FetchError, make_client
from ..model.closure import closure_indicator
from ..model.explain import explain
from ..model.hourly import build_path, official_api_path
from ..model.quantile import contributions, from_text, predict
from ..publish import (accuracy_payload, fires_payload, first_rain, first_trapped, iso, latest_entry, now_block,
                       station_payload, when_phrase, write_site_data)
from ..rows import HourlyWeather, Station
from ..sources import openmeteo
from ..store import Store
from ..weather import RAIN_POINTS

OUT_DIR = REPO_ROOT / "site-data"
WEATHER_MAX_AGE = timedelta(hours=3)
DEFAULT_SPREAD = (0.7, 1.4)  # p10/p50 and p90/p50 when a baseline without quantiles is shipped
READING_MAX_AGE = timedelta(hours=2)
ARCHIVE_EVERY_H = 6


def pm_now(observed: dict[datetime, float], official_now: tuple[datetime, float] | None,
           now_hour: datetime) -> tuple[float | None, bool]:
    """Trailing 24 h mean (µg/m³), and whether it came from real hourly data rather than DOE's API."""
    mean = trailing_mean(observed, now_hour)
    if mean is not None:
        return mean, True
    if official_now is not None:
        return api_to_ugm3(official_now[1]), False
    return None, False


def latest_reading(observed: dict[datetime, float], now_hour: datetime) -> tuple[datetime, float] | None:
    recent = [t for t in observed if now_hour - READING_MAX_AGE <= t <= now_hour]
    return (max(recent), observed[max(recent)]) if recent else None


def forecast_levels(rows: list[FeatureRow], model: tuple | None, cams_daily: dict, daily_pm: dict):
    levels: dict[str, dict[int, tuple]] = defaultdict(dict)
    contribs: dict[str, dict[str, float]] = {}
    methods: dict[str, str] = {}
    shipped, boosters = (model[0], model[2]) if model else ({}, {})
    for lead in (1, 2):
        lead_rows = [r for r in rows if r.lead == lead]
        method = shipped.get(lead, "persistence")
        if method == "model" and boosters.get(lead):
            loaded = from_text(boosters[lead])
            for row, triple in zip(lead_rows, predict(loaded, lead_rows)):
                levels[row.station_id][lead] = triple
            if lead == 1:
                for row, contrib in zip(lead_rows, contributions(loaded[0.5], lead_rows)):
                    contribs[row.station_id] = contrib
        elif method == "cams":
            for row in lead_rows:
                value = cams_corrected(row.station_id, row.issue_day, row.target_day, cams_daily, daily_pm)
                if value is not None:
                    levels[row.station_id][lead] = (value * DEFAULT_SPREAD[0], value, value * DEFAULT_SPREAD[1])
        if lead == 1:
            for row in lead_rows:
                methods[row.station_id] = method if lead in levels.get(row.station_id, {}) else "persistence"
    return dict(levels), contribs, methods


def forecast_station(station: Station, now_hour: datetime, generated_at: datetime, observed: dict[datetime, float],
                     official_now: tuple[datetime, float] | None, weather: HourlyWeather | None,
                     levels: dict[int, tuple] | None, method: str, contrib: dict | None, row: FeatureRow | None,
                     observed_daily_max: dict[date, float]) -> dict | None:
    pm0, _from_hourly = pm_now(observed, official_now, now_hour)
    if pm0 is None:
        return None
    today = now_hour.astimezone(MYT).date()
    tomorrow = (levels or {}).get(1)
    low_r, high_r = ((tomorrow[0] / tomorrow[1], tomorrow[2] / tomorrow[1]) if tomorrow and tomorrow[1] > 0
                     else DEFAULT_SPREAD)
    day_levels = {today: (pm0 * low_r, pm0, pm0 * high_r)}
    for lead in (1, 2):
        given = (levels or {}).get(lead)
        day_levels[today + timedelta(days=lead)] = given or (pm0 * DEFAULT_SPREAD[0], pm0, pm0 * DEFAULT_SPREAD[1])
    reading = latest_reading(observed, now_hour)
    path = build_path(now_hour, day_levels, weather, reading[1] if reading else None)
    official = official_api_path(path, observed, fallback=pm0)
    closure = closure_indicator(station.state, now_hour, path.times, official, observed_daily_max)
    rain_at, trapped_at = first_rain(weather, path.times), first_trapped(path)
    why = explain(contrib or {}, row, rain_window=when_phrase(rain_at, now_hour) if rain_at else None,
                  trapped_window=when_phrase(trapped_at, now_hour) if trapped_at else None) if row else []
    # "Estimated" means no live hourly reading to show or anchor on (no aqicn feed, or it is down).
    return station_payload(station, generated_at, method, reading is None, now_block(reading, official_now), path,
                           weather, official, closure, why, now_hour)


def _cams_from_forecasts(latest) -> dict[tuple[str, date], float]:
    daily = {}
    for sid, forecast in latest.items():
        series = {forecast.first_valid + timedelta(hours=i): v for i, v in enumerate(forecast.pm25) if v is not None}
        daily.update({(sid, day): value for day, value in daily_means(series).items()})
    return daily


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the website's forecast JSON.")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    settings = load_settings()
    if not settings.db_url:
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 2
    generated_at = datetime.now(timezone.utc)
    now_hour = generated_at.replace(minute=0, second=0, microsecond=0)
    today = now_hour.astimezone(MYT).date()
    try:
        store = Store.connect(settings.db_url)
    except Exception as exc:
        print(f"could not connect to the database ({type(exc).__name__})", file=sys.stderr)
        return 1
    try:
        stations = store.stations()
        issued, weather_latest = store.weather_latest()
        if issued is None or generated_at - issued > WEATHER_MAX_AGE or len(weather_latest) < len(stations):
            try:
                with make_client() as client:
                    fresh = openmeteo.fetch_weather_forecast(client, stations + list(RAIN_POINTS))
                store.save_weather_latest(fresh, generated_at)
                weather_latest = {w.station_id: w for w in fresh}
            except FetchError as exc:
                print(f"weather refresh failed; using the stored forecast ({exc})", file=sys.stderr)
        observed = {sid: {t: aqicn_aqi_to_ugm3(v) for t, v in series.items()}
                    for sid, series in store.hourly_series("aqicn", "pm25_aqi", now_hour - timedelta(hours=30)).items()}
        official_now = store.latest_obs("doe", "api", now_hour - timedelta(hours=6))
        daily_max = store.doe_daily_max(today - timedelta(days=3))
        daily_pm = store.daily_pm25(today - timedelta(days=5), today)
        cells_by_day = defaultdict(list)
        for cell in store.fire_cells(today - timedelta(days=5), today):
            cells_by_day[cell.day].append(cell)
        cams_daily = store.cams_daily(today - timedelta(days=8), today)
        cams_daily.update(_cams_from_forecasts(store.latest_cams()))
        version = store.latest_model_version()
        model = store.load_model(version) if version else None
        pm_values = {s.station_id: pm_now(observed.get(s.station_id, {}), official_now.get(s.station_id), now_hour)[0]
                     for s in stations}
        rows = build_live_rows(stations, now_hour, {k: v for k, v in pm_values.items() if v is not None}, daily_pm,
                               cells_by_day, weather_latest, cams_daily=cams_daily)
        levels, contribs, methods = forecast_levels(rows, model, cams_daily, daily_pm)
        lead1 = {r.station_id: r for r in rows if r.lead == 1}
        payloads, entries = [], []
        for s in stations:
            sid = s.station_id
            payload = forecast_station(s, now_hour, generated_at, observed.get(sid, {}), official_now.get(sid),
                                       weather_latest.get(sid), levels.get(sid), methods.get(sid, "persistence"),
                                       contribs.get(sid), lead1.get(sid),
                                       {day: v for (x, day), v in daily_max.items() if x == sid})
            if payload is not None:
                payloads.append(payload)
                entries.append(latest_entry(payload, s))
        latest_cells = [c for day in (today - timedelta(days=1), today) for c in cells_by_day.get(day, [])]
        extras = {"fires.json": fires_payload(latest_cells, generated_at),
                  "accuracy.json": accuracy_payload(model, version, store.verification_summary())}
        write_site_data(args.out, {"generated_at": iso(generated_at), "stations": entries}, payloads, extras)
        if now_hour.hour % ARCHIVE_EVERY_H == 0:
            store.save_forecast_runs(now_hour, [
                (p["id"], p["method"], now_hour, [h["pm25"] for h in p["hours"]],
                 [h["official_api"] for h in p["hours"]]) for p in payloads])
    finally:
        store.close()
    print(f"forecast: {len(payloads)} stations written to {args.out}; model version {version or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
