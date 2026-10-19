"""The website's JSON files, the contract with Plan 3.

All times are ISO-8601 UTC strings ending in "Z". Bands are good | moderate | unhealthy | very_unhealthy | hazardous.

latest.json         {"generated_at", "stations": [{"id", "name", "state", "lat", "lon", "estimated", "method",
                     "now": NOW, "next24": [band x 24], "closure": CLOSURE}]}
stations/<id>.json  {"id", "name", "state", "generated_at", "estimated", "method", "now": NOW,
                     "hours": [HOUR x 48], "days": [DAY x 3], "why": [str], "closure": CLOSURE}
fires.json          {"generated_at", "cells": [[lat, lon, frp], ...]}
accuracy.json       {"version", "backtest": {...} | null, "track_record": {...}}
map.json            {"generated_at", "times": [t x 48], "stations": [{"id", "name", "state", "lat", "lon",
                     "bands": [band x 48], "rf": [Real Feel x 48]}]}
wind.json           {"generated_at", "grid": {"lon0", "lat0", "dlon", "dlat", "nx", "ny"}, "times": [t x 16],
                     "u": [[m/s|null x nx*ny] x 16], "v": [...]}  (every 3 h; grid rows from the south, u east, v north)

NOW      {"real_feel", "real_feel_band", "pm25", "real_feel_hour", "official_api", "official_band", "official_hour"}
         (real_feel and pm25 are this hour's reading; null for stations without an hourly feed)
HOUR     {"t", "rf", "rf_low", "rf_high", "band", "pm25", "official_api", "official_low", "official_high",
          "rain_mm", "wind_from", "wind_kmh"}
DAY      {"label": "today"|"tomorrow"|"day_after", "date", "blocks": [BLOCK x 4], "best_window": WINDOW|null}
         A plan-day runs 06:00–06:00 Malaysia time; blocks are 06–12, 12–18, 18–24 and 00–06 (next morning).
BLOCK    {"start": "06:00", "end": "12:00", "status": "forecast"|"past"|"unavailable", "band", "worst_hour", "worst_rf"}
WINDOW   {"start": "15:00", "end": "19:00", "band"}  (07:00–19:00 only; good or moderate only)
CLOSURE  {"school_day", "probability": 0..1 | null, "rule": "api_above_180" | "three_days_above_150" | null}
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from . import wind
from .config import MYT
from .convert import BANDS, band, ugm3_to_real_feel
from .model.hourly import HourlyPath
from .rows import FireCell, HourlyWeather, Station

BAND_NAMES = tuple(name for name, _ in BANDS)
PLAN_BLOCKS = ((6, 12), (12, 18), (18, 24), (0, 6))
OUTDOOR_HOURS = range(7, 19)
DAY_LABELS = ("today", "tomorrow", "day_after")
MAX_FIRE_CELLS = 1500


def iso(t: datetime) -> str:
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_at(day: date, hour: int) -> datetime:
    return datetime.combine(day, time(hour), MYT).astimezone(timezone.utc)


def _hhmm(t: datetime) -> str:
    return t.astimezone(MYT).strftime("%H:00")


def plan_day_start(t: datetime) -> date:
    return (t.astimezone(MYT) - timedelta(hours=6)).date()


def best_window(times: list[datetime], rf: list[int], day: date) -> dict | None:
    index = {t: i for i, t in enumerate(times)}
    hours = [_utc_at(day, h) for h in OUTDOOR_HOURS]
    bands = [(t, band(rf[index[t]]) if t in index else None) for t in hours]
    present = [b for _, b in bands if b is not None]
    if not present:
        return None
    best = min(present, key=BAND_NAMES.index)
    if best not in ("good", "moderate"):
        return None
    run: list[datetime] = []
    longest: list[datetime] = []
    for t, b in bands:
        run = run + [t] if b == best else []
        if len(run) > len(longest):
            longest = run
    if len(longest) < 2:
        return None
    return {"start": _hhmm(longest[0]), "end": _hhmm(longest[-1] + timedelta(hours=1)), "band": best}


def day_plan(times: list[datetime], rf: list[int], now: datetime) -> list[dict]:
    index = {t: i for i, t in enumerate(times)}
    first = plan_day_start(now)
    days = []
    for k, label in enumerate(DAY_LABELS):
        day = first + timedelta(days=k)
        blocks = []
        for start_h, end_h in PLAN_BLOCKS:
            block_day = day if start_h >= 6 else day + timedelta(days=1)
            hours = [_utc_at(block_day, h) for h in range(start_h, end_h)]
            values = [(t, rf[index[t]]) for t in hours if t in index]
            block = {"start": f"{start_h:02d}:00", "end": f"{end_h % 24:02d}:00"}
            if not values:
                status = "past" if hours[-1] < times[0] else "unavailable"
                blocks.append({**block, "status": status, "band": None, "worst_hour": None, "worst_rf": None})
                continue
            worst_t, worst = max(values, key=lambda tv: tv[1])
            blocks.append({**block, "status": "forecast", "band": band(worst), "worst_hour": _hhmm(worst_t),
                           "worst_rf": int(worst)})
        days.append({"label": label, "date": day.isoformat(), "blocks": blocks,
                     "best_window": best_window(times, rf, day)})
    return days


def when_phrase(t: datetime, now: datetime) -> str:
    local, today = t.astimezone(MYT), now.astimezone(MYT).date()
    hour = local.hour
    part = "overnight" if hour < 6 else "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
    if local.date() == today:
        return {"overnight": "early this morning", "evening": "tonight"}.get(part, f"this {part}")
    if local.date() == today + timedelta(days=1):
        return "overnight" if part == "overnight" else f"tomorrow {part}"
    weekday = local.strftime("%A")
    return f"early on {weekday}" if part == "overnight" else f"on {weekday} {part}"


def first_rain(weather: HourlyWeather | None, times: list[datetime], mm: float = 1.0) -> datetime | None:
    if weather is None:
        return None
    rain = dict(zip(weather.times, weather.precip))
    return next((t for t in times[1:37] if (rain.get(t) or 0.0) >= mm), None)


def first_trapped(path: HourlyPath) -> datetime | None:
    """First early-morning hour with a shallow mixing layer and haze to trap (Real Feel above 50)."""
    return next((t for t, trapped, pm in zip(path.times[1:], path.trapped[1:], path.p50[1:])
                 if trapped and pm is not None and ugm3_to_real_feel(pm) > 50 and 5 <= t.astimezone(MYT).hour <= 10), None)


def now_block(reading: tuple[datetime, float] | None, official: tuple[datetime, float] | None,
              others: dict[str, float] | None = None) -> dict:
    """Real Feel is the hour's overall AQI: the highest of its pollutants' US AQI numbers, as aqicn reports them.

    `others` holds the same hour's PM10, ozone, NO2, SO2 and CO numbers; PM2.5 comes from the reading itself."""
    rf = main = None
    if reading:
        sub = {"pm25": ugm3_to_real_feel(reading[1]), **(others or {})}
        main = max(sub, key=sub.get)
        rf = round(sub[main])
    return {
        "real_feel": rf, "real_feel_band": band(rf) if rf is not None else None, "main_pollutant": main,
        "pm25": round(reading[1], 1) if reading else None, "real_feel_hour": iso(reading[0]) if reading else None,
        "official_api": round(official[1]) if official else None,
        "official_band": band(official[1]) if official else None,
        "official_hour": iso(official[0]) if official else None,
    }


def _round(value) -> int | None:
    return None if value is None else int(round(value))


def station_payload(station: Station, generated_at: datetime, method: str, estimated: bool, now: dict,
                    path: HourlyPath, weather: HourlyWeather | None, official: tuple[list, list, list],
                    closure: dict, why: list[str], now_hour: datetime) -> dict:
    rf = [int(round(ugm3_to_real_feel(v))) for v in path.p50]
    rf_low = [int(round(ugm3_to_real_feel(v))) for v in path.p10]
    rf_high = [int(round(ugm3_to_real_feel(v))) for v in path.p90]
    if now.get("main_pollutant") not in (None, "pm25") and rf and now["real_feel"] > rf[0]:
        # Only PM2.5 is forecast; when another pollutant leads this hour, the first hour shows the overall figure.
        rf[0] = now["real_feel"]
        rf_high[0] = max(rf_high[0], rf[0])
    wx = {t: i for i, t in enumerate(weather.times)} if weather else {}

    def at(series: list | None, t: datetime):
        return series[wx[t]] if series is not None and t in wx else None

    hours = [{
        "t": iso(t), "rf": rf[i], "rf_low": rf_low[i], "rf_high": rf_high[i], "band": band(rf[i]),
        "pm25": round(path.p50[i], 1), "official_api": _round(official[1][i]), "official_low": _round(official[0][i]),
        "official_high": _round(official[2][i]), "rain_mm": at(weather.precip if weather else None, t),
        "wind_from": at(weather.wind120_from if weather else None, t),
        "wind_kmh": at(weather.wind10 if weather else None, t),
    } for i, t in enumerate(path.times)]
    return {"id": station.station_id, "name": station.name, "state": station.state, "generated_at": iso(generated_at),
            "estimated": estimated, "method": method, "now": now, "hours": hours,
            "days": day_plan(path.times, rf, now_hour), "why": why, "closure": closure}


def latest_entry(payload: dict, station: Station) -> dict:
    return {"id": payload["id"], "name": payload["name"], "state": payload["state"], "lat": station.lat,
            "lon": station.lon, "estimated": payload["estimated"], "method": payload["method"], "now": payload["now"],
            "next24": [h["band"] for h in payload["hours"][:24]], "closure": payload["closure"]}


def wind_payload(field: dict, now_hour: datetime, generated_at: datetime, hours: int = 48) -> dict:
    """wind.json: the wind field every 3 hours from now for the next 48 hours (the map interpolates between)."""
    index = {t: k for k, t in enumerate(field["times"])}
    frames = [iso(now_hour + timedelta(hours=h)) for h in range(0, hours, wind.FRAME_STEP_H)]
    keep = [(t, index[t]) for t in frames if t in index]
    return {"generated_at": iso(generated_at),
            "grid": {"lon0": wind.LON0, "lat0": wind.LAT0, "dlon": wind.DLON, "dlat": wind.DLAT, "nx": wind.NX,
                     "ny": wind.NY},
            "times": [t for t, _ in keep], "u": [field["u"][k] for _, k in keep], "v": [field["v"][k] for _, k in keep]}


def map_payload(payloads: list[dict], stations: dict[str, Station], generated_at: datetime) -> dict:
    """map.json: every station's 48 hourly bands and Real Feel numbers, for the map's time slider (wind: wind.json).

    "readings" is the oldest and newest hour of the stations' latest readings: the first slot is the current
    clock hour, but a feed that has not posted this hour yet still shows the hour before."""
    read = sorted({p["now"]["real_feel_hour"] for p in payloads if p["now"].get("real_feel_hour")})
    return {"generated_at": iso(generated_at),
            "times": [h["t"] for h in payloads[0]["hours"]] if payloads else [],
            "readings": [read[0], read[-1]] if read else None,
            "stations": [{"id": p["id"], "name": p["name"], "state": p["state"],
                          "lat": stations[p["id"]].lat, "lon": stations[p["id"]].lon,
                          "bands": [h["band"] for h in p["hours"]],
                          "rf": [h["rf"] for h in p["hours"]]} for p in payloads]}


def fires_payload(cells: list[FireCell], generated_at: datetime) -> dict:
    strongest = sorted(cells, key=lambda c: -c.frp_sum)[:MAX_FIRE_CELLS]
    return {"generated_at": iso(generated_at),
            "cells": [[round(c.lat_bin + 0.125, 3), round(c.lon_bin + 0.125, 3), round(c.frp_sum, 1)] for c in strongest]}


def accuracy_payload(model: tuple | None, version: str | None, track_record: dict) -> dict:
    backtest = None
    if model:
        _methods, report, _boosters = model
        backtest = {lead: {k: entry[k] for k in ("method", "meets_target", "test_from", "test_to", "model",
                                                 "persistence", "cams")}
                    for lead, entry in report.get("leads", {}).items()}
    return {"version": version, "backtest": backtest, "track_record": track_record}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_station(obj: dict) -> None:
    for key in ("id", "name", "state", "generated_at", "estimated", "method", "now", "hours", "days", "why", "closure"):
        _require(key in obj, f"station file missing {key!r}")
    _require(len(obj["hours"]) == 48, f"{obj['id']}: needs 48 hours, has {len(obj['hours'])}")
    for h in obj["hours"]:
        _require(isinstance(h.get("rf"), int) and h.get("band") in BAND_NAMES, f"{obj['id']}: bad hour {h.get('t')}")
    _require(len(obj["days"]) == 3 and all(len(d["blocks"]) == 4 for d in obj["days"]),
             f"{obj['id']}: needs 3 days of 4 blocks")
    for d in obj["days"]:
        for b in d["blocks"]:
            _require(b["band"] in BAND_NAMES or b["band"] is None, f"{obj['id']}: bad block band")
    _require(isinstance(obj["why"], list), f"{obj['id']}: why must be a list")
    probability = obj["closure"].get("probability")
    _require(probability is None or 0 <= probability <= 1, f"{obj['id']}: closure probability out of range")


def validate_latest(obj: dict) -> None:
    _require(isinstance(obj.get("stations"), list) and len(obj["stations"]) > 0, "latest.json has no stations")
    for s in obj["stations"]:
        for key in ("id", "name", "state", "lat", "lon", "estimated", "method", "now", "next24", "closure"):
            _require(key in s, f"latest.json station missing {key!r}")
        _require(len(s["next24"]) == 24 and all(b in BAND_NAMES for b in s["next24"]), f"{s['id']}: bad next24")


def write_site_data(out_dir: Path, latest: dict, stations: list[dict], extras: dict[str, object]) -> None:
    validate_latest(latest)
    for payload in stations:
        validate_station(payload)

    def dump(obj) -> str:
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False)

    # Serialise everything before writing anything: a NaN anywhere publishes nothing.
    files = {"latest.json": dump(latest)}
    files.update({f"stations/{payload['id']}.json": dump(payload) for payload in stations})
    files.update({name: dump(obj) for name, obj in extras.items()})
    out_dir = Path(out_dir)
    (out_dir / "stations").mkdir(parents=True, exist_ok=True)

    for name, text in files.items():
        (out_dir / name).write_text(text, encoding="utf-8")
