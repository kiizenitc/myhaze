# MYHaze Plan 2: Forecast Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the hourly archive into a 48-hour, hour-by-hour Real Feel forecast for all 68 stations. That covers fire hotspots, unit conversion, a trained and backtested model, the official API forecast, the school-closure indicator and a plain-language "why", all published as JSON files that Plan 3's website reads.

**Architecture:**
- **Inputs.** New ingestion adds NASA FIRMS hotspots (aggregated into 0.25° cells per day) and Open-Meteo weather. Weather comes from two sources: archived real day-1 and day-2 forecasts for training, and the live forecast for inference.
- **Daily model.** A pooled LightGBM quantile model (10/50/90%) predicts each station's daily-mean PM2.5 for tomorrow and the day after. Its features are built by one shared code path for training and live use, so the backtest can't cheat with hindsight.
- **Hourly path.** A shaper turns the daily levels into a 48-hour path. It's anchored on the live aqicn hourly reading and shaped by forecast mixing height and rain.
- **Outputs.** From the path: the official API forecast (24-hour rolling mean), the closure probability, and the explanation sentences.
- **Jobs:**
  - **Weekly train:** retrains, backtests, stores the model and commits a report.
  - **Hourly forecast:** writes `site-data/*.json`.
  - **Daily verify:** scores yesterday's forecasts for the public track record.

**Tech Stack:** Python 3.12 (uv), httpx, psycopg 3, numpy, LightGBM 4.7, pytest; Supabase Postgres; GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-15-myhaze-design.md` (§4–§7, §11). **Builds on:** Plan 1 (`docs/superpowers/plans/2026-10-15-myhaze-plan-1-hourly-archive.md`), which is merged on `main`.

**This is plan 2 of 3.** Plan 3 (website and Cloudflare deploy) consumes the JSON contract defined in Task 9.

## Global Constraints

- Python 3.12 via uv. New runtime dependencies are limited to `numpy` and `lightgbm` (plus Plan 1's `httpx` and `psycopg[binary]`). On macOS, LightGBM needs `brew install libomp`.
- AGPL-3.0. Nothing is copied from `herr-hollis/Malaysia-Haze-Monitor`.
- **Malaysian air-quality data from 1 July 2026 onward only.** Fires (Indonesia and Malaysia) and weather are inputs, not air-quality data.
- Secrets live only in env / `.env` / GitHub secrets. `FIRMS_MAP_KEY` sits **in the URL path**, so every FIRMS call goes through `get_text(..., label=...)`, which never prints URLs.
- aqicn data (hourly or daily CSV) is never published as history. Site JSON may contain only *current* readings and *our own* forecasts. Every new table has row-level security on.
- All stored timestamps are UTC `timestamptz`; "days" are **Malaysia calendar days (UTC+8)** unless a column says UTC.
- Bands (Malaysian API): good ≤50, moderate 51–100, unhealthy 101–200, very_unhealthy 201–300, hazardous >300.
- **Real Feel** = 1-hour PM2.5 converted with DOE's PM2.5 table. **Official API** = 24-hour rolling mean, same table. Never label one as the other.
- Accuracy targets (spec §6.6): D+1 band accuracy ≥0.90 **and** POD(unhealthy or worse) ≥0.90, and the model must beat persistence and corrected CAMS. If it doesn't, the best method ships and the true numbers are published.
- GitHub Actions are pinned to commit SHAs (Plan 1 test `test_every_github_action_is_pinned_to_a_commit_sha` enforces this):
  - `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` # v7.0.1
  - `astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7` # v10.2.0
  - `actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` # v7.0.1
- Commits are authored by the repo-local noreply identity, and each message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Work happens on branch `plan-2-forecast`.

### Deliberate changes from the spec (reasons)

- **DOE's PM2.5 breakpoints are calibrated, not hard-coded** (spec §5 said "fitted and confirmed"). No official PM2.5 table could be found online; DOE's 2021 deck predates PM2.5 in the API. Task 2 scores four published candidate tables against DOE's own numbers and picks the best.
- **The training features use 120 m wind, not 925/850 hPa wind, and mixing height is not a daily-model feature.** Open-Meteo's archive of past forecasts has no pressure-level winds and no mixing height. Using analysis values would leak hindsight into the backtest. Mixing height still shapes the hourly path, from the live forecast.
- **The fire features use the last complete UTC day before issue time** (spec: "day D"). This keeps training and live definitions identical.
- **The latest training run is always promoted** (spec: "only if it passes and beats the current one"). Successive backtests use different test windows, so comparing them isn't like-for-like. Every version's report is kept and published.
- **Forecast runs are archived every 6 hours (00/06/12/18 UTC), not every hour.** Hourly archiving would need about 360 MB a year, against Supabase's 500 MB. Six-hourly runs are enough for verification, and the published JSON always comes from the latest hourly run.
- **The closure probability is `max(rule 180, rule 150×3 days)`, not a joint probability.** The two rules share the same days, so they're strongly correlated. Max is simple, never overstates either rule, and the site labels it an indicator.

## Review Focus

1. **Hindsight leakage.** A feature for issue day D must not use air-quality data from after D, or fire cells from day D or later. Pinned by `test_features_do_not_change_when_future_data_changes` (Task 5).
2. **Missing inputs in live use:**
   - A station with no aqicn feed (5 stations), no weather, or no fires yesterday must still get a forecast, flagged `estimated`, never a crash or an empty file.
   - The site's JSON must be valid even when the model isn't trained yet.
   - Pinned by `test_station_payload_without_hourly_feed_is_estimated` (Task 10), `test_forecast_without_a_model_falls_back_to_persistence` (Task 10) and the schema validators (Task 9).
3. **Time zones at day edges.** The 6-hour blocks run 06–12, 12–18, 18–24, 00–06 MYT and the school day is a Malaysia date, but all stored times are UTC. A run at 23:30 MYT must put the 00:00–06:00 block in the right plan-day. Pinned by `test_day_plan_blocks_follow_malaysia_time` (Task 9) and `test_next_school_day_respects_state_weeks` (Task 8).
4. **Unit-conversion edges:** 0, values beyond a table's top (extrapolate, never crash), None, and the round trip index→concentration→index. Pinned in Task 2.
5. **Upstream shape changes.** A FIRMS reply that isn't CSV (bad key, quota), aqicn CSV quirks (spaces, `2026/7/1` dates, blank cells), and Open-Meteo location-count mismatches must raise `FetchError` or skip the row; they must never write garbage. Pinned in Tasks 1, 3 and 4.

---

## File structure

```
pipeline/myhaze/
  config.py              + firms_key
  http.py                + get_text (shared retry core with get_json)
  geo.py                 haversine_km, bearing_deg, region_of (fire-source regions)       [new]
  rows.py                + FireCell, HourlyWeather
  sources/firms.py       FIRMS area CSV → FireCell grid; availability → NRT/SP choice  [new]
  sources/aqicn_csv.py   aqicn daily CSV export parser                                 [new]
  sources/openmeteo.py   + weather forecast, previous-runs history, CAMS history
  convert.py             US AQI / µg/m³ / Malaysian API tables, bands, calibrated pick  [new]
  calibration.py         choose aqicn and DOE tables from archived data               [new]
  calibration.json       the chosen tables (committed)                                [new]
  daily.py               daily and trailing means from hourly series                  [new]
  weather.py             WeatherDay daily summaries, rain points                      [new]
  features.py            FeatureRow builder shared by training and live              [new]
  metrics.py             band accuracy, POD, FAR, MAE, coverage                       [new]
  baselines.py           persistence, corrected CAMS                                  [new]
  model/__init__.py
  model/quantile.py      LightGBM quantile fit/predict/contributions/serialise        [new]
  model/backtest.py      splits, comparison, method choice, report rendering         [new]
  model/hourly.py        48 h path shaper and official API path                      [new]
  model/closure.py       school weeks and closure probability                        [new]
  model/explain.py       plain-language "why" sentences                               [new]
  publish.py             site JSON builders and validators, day plan, best window     [new]
  store.py               + methods for every new table
  jobs/archive.py        + fires step
  jobs/backfill.py       fires / weather / cams history                               [new]
  jobs/calibrate.py      writes calibration.json                                      [new]
  jobs/load_daily.py     aqicn CSVs + archive daily means → daily_pm25               [new]
  jobs/train.py          weekly train + backtest + report                            [new]
  jobs/forecast.py       hourly forecast → site-data/                                [new]
  jobs/verify.py         daily verification                                           [new]
pipeline/tests/          one test module per new module (named below)
supabase/migrations/0002_fires.sql 0003_daily.sql 0004_weather.sql 0005_models.sql 0006_forecasts.sql
.github/workflows/archive.yml (+FIRMS_MAP_KEY)  forecast.yml  train.yml  verify.yml
docs/backtest/latest.md latest.json (written by train job)
```

All commands run from the repo root `/Users/ryanchuah/Claude Code/MYHaze` with `uv --directory pipeline …`. Unit suite: `uv --directory pipeline run pytest -q`. Full suite including the database: `uv --directory pipeline run pytest -m "integration or not integration" -q`.

---

### Task 1: FIRMS fire hotspots (geo helpers, source, storage, hourly step, backfill)

**Files:**
- Create: `pipeline/myhaze/geo.py`, `pipeline/myhaze/sources/firms.py`, `pipeline/myhaze/jobs/backfill.py`, `supabase/migrations/0002_fires.sql`, `pipeline/tests/test_geo.py`, `pipeline/tests/test_firms.py`
- Modify: `pipeline/myhaze/config.py`, `pipeline/myhaze/http.py`, `pipeline/myhaze/rows.py`, `pipeline/myhaze/sources/aqicn.py` (use `geo.haversine_km`), `pipeline/myhaze/store.py`, `pipeline/myhaze/jobs/archive.py`, `pipeline/tests/fakes.py`, `pipeline/tests/test_http.py`, `pipeline/tests/test_archive_job.py`, `pipeline/tests/test_store_integration.py`, `.github/workflows/archive.yml`

**Interfaces:**
- Produces:
  - `Settings.firms_key: str | None` (third field, default `None`; positional two-argument construction still works).
  - `http.get_text(client, url, params=None, *, label=None, attempts=3, backoff_s=2.0) -> str`
  - `geo.haversine_km(lat1, lon1, lat2, lon2) -> float`
  - `geo.bearing_deg(lat1, lon1, lat2, lon2) -> float` (0 = north, clockwise)
  - `geo.region_of(lat, lon) -> str`, one of `"sumatra" | "kalimantan" | "peninsular" | "my_borneo" | "other"`
  - `rows.FireCell(day: date, lat_bin: float, lon_bin: float, frp_sum: float, detections: int)`. `day` is a UTC date; bins are the south-west corner of a 0.25° cell.
  - `firms.GRID_DEG = 0.25`, `firms.SENSORS = ("VIIRS_SNPP", "VIIRS_NOAA20")`
  - `firms.parse_area_csv(text) -> list[tuple[date, float, float, float]]` (day, lat, lon, frp)
  - `firms.to_cells(detections) -> list[FireCell]`
  - `firms.parse_availability(text) -> dict[str, tuple[date, date]]`
  - `firms.source_for(sensor, day, availability) -> str | None`
  - `firms.fetch_availability(client, key)`
  - `firms.fetch_cells(client, key, start: date, end: date, availability) -> list[FireCell]`
  - `Store.upsert_fire_cells(cells) -> int`
  - `Store.fire_cells(start: date, end: date) -> list[FireCell]`
  - `archive.archive_fires(client, store, settings, now_utc) -> dict`, which runs as step `"fires"` after `"cams"`
  - `backfill.BACKFILLS: dict[str, Callable[[client, store, settings, date, date], dict]]`
  - `backfill.main(argv) -> int`

- [ ] **Step 1: Write the failing tests**

`pipeline/tests/test_geo.py`:

```python
import pytest

from myhaze.geo import bearing_deg, haversine_km, region_of


@pytest.mark.parametrize("name,lat,lon,region", [
    ("Dumai, Riau", 1.67, 101.45, "sumatra"),
    ("Jambi", -1.6, 103.6, "sumatra"),
    ("Banda Aceh", 5.55, 95.32, "sumatra"),
    ("Klang", 3.04, 101.45, "peninsular"),
    ("Port Dickson", 2.52, 101.80, "peninsular"),
    ("Penang", 5.41, 100.33, "peninsular"),
    ("Palangkaraya", -2.21, 113.92, "kalimantan"),
    ("Pontianak", -0.03, 109.33, "kalimantan"),
    ("Kuching", 1.55, 110.35, "my_borneo"),
    ("Tawau", 4.25, 117.89, "my_borneo"),
    ("Manila", 14.6, 121.0, "other"),
])
def test_region_of_places(name, lat, lon, region):
    assert region_of(lat, lon) == region, name


def test_bearing_and_distance():
    assert bearing_deg(0, 100, 1, 100) == pytest.approx(0, abs=0.01)    # due north
    assert bearing_deg(0, 100, 0, 101) == pytest.approx(90, abs=0.01)   # due east
    assert bearing_deg(3, 101, 2, 100) == pytest.approx(225, abs=0.5)   # south-west
    assert haversine_km(0, 100, 1, 100) == pytest.approx(111.2, abs=0.2)
```

`pipeline/tests/test_firms.py`:

```python
from datetime import date

import httpx
import pytest

from myhaze.http import FetchError, make_client
from myhaze.sources import firms

CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
    "-2.21,113.92,330.1,0.4,0.4,2026-10-14,0542,N,VIIRS,n,2.0NRT,290.1,12.5,D\n"
    "-2.24,113.99,331.0,0.4,0.4,2026-10-14,0542,N,VIIRS,h,2.0NRT,291.0,7.5,D\n"
    "-2.21,113.92,300.0,0.4,0.4,2026-10-14,0542,N,VIIRS,l,2.0NRT,280.0,99.0,D\n"
    "1.67,101.45,333.3,0.4,0.4,2026-10-14,1812,N,VIIRS,n,2.0NRT,292.2,3.0,N\n"
    "oops,101.45,333.3,0.4,0.4,2026-10-14,1812,N,VIIRS,n,2.0NRT,292.2,3.0,N\n"
)
AVAILABILITY = (
    "data_id,min_date,max_date\n"
    "VIIRS_SNPP_NRT,2026-08-15,2026-10-15\n"
    "VIIRS_SNPP_SP,2012-01-20,2026-08-31\n"
    "VIIRS_NOAA20_NRT,2026-08-15,2026-10-15\n"
    "VIIRS_NOAA20_SP,2018-04-01,2026-08-31\n"
)


def test_parse_area_csv_skips_low_confidence_and_bad_rows():
    rows = firms.parse_area_csv(CSV)
    assert rows == [(date(2026, 10, 14), -2.21, 113.92, 12.5), (date(2026, 10, 14), -2.24, 113.99, 7.5),
                    (date(2026, 10, 14), 1.67, 101.45, 3.0)]


def test_parse_area_csv_rejects_non_csv_replies():
    with pytest.raises(FetchError):
        firms.parse_area_csv("Invalid MAP_KEY.")


def test_to_cells_sums_frp_per_quarter_degree_cell():
    cells = firms.to_cells(firms.parse_area_csv(CSV))
    assert [(c.day, c.lat_bin, c.lon_bin, c.frp_sum, c.detections) for c in cells] == [
        (date(2026, 10, 14), -2.25, 113.75, 20.0, 2),
        (date(2026, 10, 14), 1.5, 101.25, 3.0, 1),
    ]


def test_source_for_prefers_nrt_then_sp():
    availability = firms.parse_availability(AVAILABILITY)
    assert firms.source_for("VIIRS_SNPP", date(2026, 10, 1), availability) == "VIIRS_SNPP_NRT"
    assert firms.source_for("VIIRS_SNPP", date(2026, 7, 1), availability) == "VIIRS_SNPP_SP"
    assert firms.source_for("VIIRS_SNPP", date(2027, 1, 1), availability) is None


def test_fetch_cells_uses_one_request_per_sensor_when_nrt_covers_the_range():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, text=CSV.splitlines()[0] + "\n")

    availability = firms.parse_availability(AVAILABILITY)
    firms.fetch_cells(make_client(transport=httpx.MockTransport(handler)), "KEY123",
                      date(2026, 8, 30), date(2026, 9, 2), availability)
    assert paths == [
        "/api/area/csv/KEY123/VIIRS_SNPP_NRT/95,-6,120,8/4/2026-08-30",
        "/api/area/csv/KEY123/VIIRS_NOAA20_NRT/95,-6,120,8/4/2026-08-30",
    ]


def test_fetch_cells_switches_to_sp_before_nrt_coverage():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, text="latitude,longitude,acq_date,confidence,frp\n")

    availability = firms.parse_availability(AVAILABILITY)
    firms.fetch_cells(make_client(transport=httpx.MockTransport(handler)), "K", date(2026, 8, 13), date(2026, 8, 16),
                      availability)
    assert paths[:2] == ["/api/area/csv/K/VIIRS_SNPP_SP/95,-6,120,8/2/2026-08-13",
                         "/api/area/csv/K/VIIRS_SNPP_NRT/95,-6,120,8/2/2026-08-15"]


def test_fetch_cells_errors_never_contain_the_key():
    availability = firms.parse_availability(AVAILABILITY)
    with pytest.raises(FetchError) as info:
        firms.fetch_cells(make_client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
                          "KEY123", date(2026, 9, 1), date(2026, 9, 1), availability)
    assert "KEY123" not in str(info.value)
```

Append to `pipeline/tests/test_http.py`:

```python
def test_get_text_returns_text_and_hides_secret_paths():
    from myhaze.http import get_text

    assert get_text(client_for(lambda r: httpx.Response(200, text="a,b\n1,2\n")), "https://x.test/") == "a,b\n1,2\n"
    with pytest.raises(FetchError) as info:
        get_text(client_for(lambda r: httpx.Response(503)), "https://x.test/api/SECRETKEY/x", label="FIRMS area")
    assert str(info.value) == "FIRMS area failed after 3 attempts: HTTP 503"
```

Append to `pipeline/tests/test_archive_job.py`:

```python
def test_fires_step_stores_cells_once_per_hour():
    from tests.test_firms import AVAILABILITY, CSV

    store = FakeStore(stations=[KANGAR], aqicn={"CA01R": 3001})
    routes = dict(HEALTHY, **{"/data_availability/csv/FK/ALL": AVAILABILITY,
                              "/v1/air-quality": fixtures.CAMS_TWO_STATIONS[0]})

    def handler(request):
        for suffix, reply in routes.items():
            if request.url.path.endswith(suffix):
                return httpx.Response(200, json=reply) if not isinstance(reply, str) else httpx.Response(200, text=reply)
        if "/api/area/csv/FK/" in request.url.path:
            return httpx.Response(200, text=CSV)
        return httpx.Response(404)

    settings = Settings("tok123", "postgresql://unused", "FK")
    client = make_client(transport=httpx.MockTransport(handler))
    result = archive.run(NOW, settings, client, store)
    assert result.details["fires"]["status"] == "ok"
    assert len(store.fire_cells_store) == 2

    later = archive.archive_fires(client, store, settings, NOW.replace(minute=20))
    assert later == {"status": "skipped", "reason": "fetched at the start of the hour"}


def test_fires_step_is_skipped_without_a_key():
    detail = archive.archive_fires(routed_client(HEALTHY, []), FakeStore(), SETTINGS, NOW)
    assert detail == {"status": "skipped", "reason": "FIRMS_MAP_KEY not set"}
```

Append to `pipeline/tests/test_store_integration.py`:

```python
def test_fire_cells_roundtrip_and_upsert(store):
    from datetime import date

    from myhaze.rows import FireCell

    day = date(1999, 1, 1)
    try:
        assert store.upsert_fire_cells([FireCell(day, -2.25, 113.75, 20.0, 2)]) == 1
        store.upsert_fire_cells([FireCell(day, -2.25, 113.75, 25.5, 3)])
        assert store.fire_cells(day, day) == [FireCell(day, -2.25, 113.75, 25.5, 3)]
    finally:
        store.conn.execute("delete from fire_grid_daily where day = %s", (day,))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest -q 2>&1 | tail -3`
Expected: FAIL. Collection errors for `myhaze.geo` and `myhaze.sources.firms`, plus failures in `test_http`/`test_archive_job`.

- [ ] **Step 3: Write the implementation**

`pipeline/myhaze/geo.py`:

```python
"""Distances, bearings and the coarse fire-source regions used in features and explanations."""
from __future__ import annotations

import math


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2: 0 = north, 90 = east."""
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def _interp(x: float, points: list[tuple[float, float]]) -> float:
    if x <= points[0][0]:
        return points[0][1]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y0 + (x - x0) * (y1 - y0) / (x1 - x0)
    return points[-1][1]


# A line down the Strait of Malacca: Sumatra lies west of it, Peninsular Malaysia east.
def _strait_lon(lat: float) -> float:
    return 104.0 - (lat - 1.0) * 1.6


# Rough Malaysia–Indonesia land border on Borneo (latitude by longitude); north of it is Sarawak/Sabah/Brunei.
_BORNEO_BORDER = [(108.5, 1.0), (112.5, 1.1), (114.8, 2.0), (116.0, 4.3), (116.5, 4.1), (119.5, 4.1)]


def region_of(lat: float, lon: float) -> str:
    if 108.5 <= lon <= 119.5 and -4.5 <= lat <= 7.5:
        return "my_borneo" if lat > _interp(lon, _BORNEO_BORDER) else "kalimantan"
    if 1.25 <= lat <= 6.75 and 99.5 <= lon <= 104.6 and lon > _strait_lon(lat):
        return "peninsular"
    if 95.0 <= lon <= 106.5 and -6.0 <= lat <= 6.0 and (lat < 1.25 or lon <= _strait_lon(lat)):
        return "sumatra"
    return "other"
```

In `pipeline/myhaze/sources/aqicn.py`, replace the local `haversine_km` definition with an import, keeping the name available as `aqicn.haversine_km`:

```python
from ..geo import haversine_km  # noqa: F401  (re-exported for callers of aqicn.haversine_km)
```

Delete the `def haversine_km(...)` block in `aqicn.py`.

`pipeline/myhaze/config.py`: add the field and read it.

```python
@dataclass(frozen=True)
class Settings:
    aqicn_token: str | None
    db_url: str | None
    firms_key: str | None = None
```

```python
    return Settings(
        aqicn_token=os.environ.get("AQICN_TOKEN") or None,
        db_url=os.environ.get("SUPABASE_DB_URL") or None,
        firms_key=os.environ.get("FIRMS_MAP_KEY") or None,
    )
```

`pipeline/myhaze/http.py`: replace `get_json` with a shared core plus two thin wrappers.

```python
def _get(client: httpx.Client, url: str, params: dict | None, label: str | None,
         attempts: int, backoff_s: float, parse):
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            return parse(response)
        except (httpx.HTTPError, ValueError) as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(backoff_s * (attempt + 1))
    name = label or urlsplit(url).netloc
    raise FetchError(f"{name} failed after {attempts} attempts: {_describe(last)}") from None


def get_json(client: httpx.Client, url: str, params: dict | None = None, *,
             label: str | None = None, attempts: int = 3, backoff_s: float = 2.0):
    return _get(client, url, params, label, attempts, backoff_s, lambda response: response.json())


def get_text(client: httpx.Client, url: str, params: dict | None = None, *,
             label: str | None = None, attempts: int = 3, backoff_s: float = 2.0) -> str:
    return _get(client, url, params, label, attempts, backoff_s, lambda response: response.text)
```

Append to `pipeline/myhaze/rows.py`:

```python
@dataclass(frozen=True)
class FireCell:
    """FIRMS fire radiative power summed over a 0.25° cell for one UTC day (bins = south-west corner)."""
    day: date
    lat_bin: float
    lon_bin: float
    frp_sum: float
    detections: int
```

Change the `rows.py` import line to `from datetime import date, datetime`.

`pipeline/myhaze/sources/firms.py`:

```python
"""NASA FIRMS VIIRS active fires, aggregated to 0.25° cells per UTC day.

The MAP_KEY travels in the URL path, so every call goes through get_text with a label: errors never print URLs.
Only the two satellites with both near-real-time (NRT) and archive (SP) products are used, so training
history and live data come from the same instruments.
"""
from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from datetime import date, timedelta

import httpx

from ..http import FetchError, get_text
from ..rows import FireCell

BASE = "https://firms.modaps.eosdis.nasa.gov/api"
AREA = "95,-6,120,8"  # west,south,east,north: Sumatra, Peninsular Malaysia, Borneo
SENSORS = ("VIIRS_SNPP", "VIIRS_NOAA20")
GRID_DEG = 0.25
MAX_DAYS = 5  # FIRMS allows 1-5 days per area request


def parse_area_csv(text: str) -> list[tuple[date, float, float, float]]:
    if not text.lstrip().startswith("latitude"):
        raise FetchError("FIRMS: reply was not hotspot CSV")
    detections = []
    for row in csv.DictReader(io.StringIO(text)):
        if (row.get("confidence") or "").strip().lower() in ("l", "low"):
            continue
        try:
            detections.append((date.fromisoformat(row["acq_date"].strip()), float(row["latitude"]),
                               float(row["longitude"]), float(row["frp"])))
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
    return detections


def to_cells(detections: list[tuple[date, float, float, float]]) -> list[FireCell]:
    totals: dict[tuple[date, float, float], list] = defaultdict(lambda: [0.0, 0])
    for day, lat, lon, frp in detections:
        key = (day, math.floor(lat / GRID_DEG) * GRID_DEG, math.floor(lon / GRID_DEG) * GRID_DEG)
        totals[key][0] += max(frp, 0.0)
        totals[key][1] += 1
    return [FireCell(day, lat_bin, lon_bin, round(frp_sum, 2), count)
            for (day, lat_bin, lon_bin), (frp_sum, count) in sorted(totals.items())]


def parse_availability(text: str) -> dict[str, tuple[date, date]]:
    availability = {}
    for row in csv.DictReader(io.StringIO(text)):
        try:
            availability[row["data_id"].strip()] = (date.fromisoformat(row["min_date"].strip()),
                                                    date.fromisoformat(row["max_date"].strip()))
        except (AttributeError, KeyError, ValueError):
            continue
    if not availability:
        raise FetchError("FIRMS: data availability unreadable")
    return availability


def source_for(sensor: str, day: date, availability: dict[str, tuple[date, date]]) -> str | None:
    for suffix in ("NRT", "SP"):
        span = availability.get(f"{sensor}_{suffix}")
        if span and span[0] <= day <= span[1]:
            return f"{sensor}_{suffix}"
    return None


def fetch_availability(client: httpx.Client, key: str) -> dict[str, tuple[date, date]]:
    return parse_availability(get_text(client, f"{BASE}/data_availability/csv/{key}/ALL", label="FIRMS availability"))


def fetch_cells(client: httpx.Client, key: str, start: date, end: date,
                availability: dict[str, tuple[date, date]]) -> list[FireCell]:
    detections = []
    for sensor in SENSORS:
        day = start
        while day <= end:
            source = source_for(sensor, day, availability)
            if source is None:
                day += timedelta(days=1)
                continue
            span = 1
            while (span < MAX_DAYS and day + timedelta(days=span) <= end
                   and source_for(sensor, day + timedelta(days=span), availability) == source):
                span += 1
            text = get_text(client, f"{BASE}/area/csv/{key}/{source}/{AREA}/{span}/{day.isoformat()}",
                            label="FIRMS area")
            detections += parse_area_csv(text)
            day += timedelta(days=span)
    return to_cells(detections)
```

`supabase/migrations/0002_fires.sql`:

```sql
-- FIRMS fire radiative power per 0.25° cell per UTC day. Private like every other table.
create table fire_grid_daily (
  day date not null,
  lat_bin real not null,
  lon_bin real not null,
  frp_sum real not null,
  detections integer not null,
  primary key (day, lat_bin, lon_bin)
);
alter table fire_grid_daily enable row level security;
```

Append to the `Store` class in `pipeline/myhaze/store.py` (and add `from datetime import date, datetime` plus `FireCell` to the rows import):

```python
    def upsert_fire_cells(self, cells: list[FireCell]) -> int:
        if cells:
            with self.conn.transaction(), self.conn.cursor() as cur:
                cur.executemany(
                    "insert into fire_grid_daily (day, lat_bin, lon_bin, frp_sum, detections) values (%s, %s, %s, %s, %s) "
                    "on conflict (day, lat_bin, lon_bin) do update set "
                    "frp_sum = excluded.frp_sum, detections = excluded.detections",
                    [(c.day, c.lat_bin, c.lon_bin, c.frp_sum, c.detections) for c in cells],
                )
        return len(cells)

    def fire_cells(self, start: date, end: date) -> list[FireCell]:
        rows = self.conn.execute(
            "select day, lat_bin, lon_bin, frp_sum, detections from fire_grid_daily "
            "where day between %s and %s order by day, lat_bin, lon_bin", (start, end)).fetchall()
        return [FireCell(day, float(lat), float(lon), float(frp), int(n)) for day, lat, lon, frp, n in rows]
```

In `pipeline/tests/fakes.py`, add `self.fire_cells_store = {}` to `FakeStore.__init__` and append these methods:

```python
    def upsert_fire_cells(self, cells):
        for c in cells:
            self.fire_cells_store[(c.day, c.lat_bin, c.lon_bin)] = c
        return len(cells)

    def fire_cells(self, start, end):
        return sorted((c for c in self.fire_cells_store.values() if start <= c.day <= end),
                      key=lambda c: (c.day, c.lat_bin, c.lon_bin))
```

In `pipeline/myhaze/jobs/archive.py`:
- Add the import `from ..sources import aqicn, doe, firms, openmeteo`.
- Add the function below.
- Register `"fires": lambda: archive_fires(client, store, settings, now_utc),` as the last entry in `steps`.

```python
def archive_fires(client, store, settings, now_utc: datetime) -> dict:
    if not settings.firms_key:
        return {"status": "skipped", "reason": "FIRMS_MAP_KEY not set"}
    if now_utc.minute >= 15:
        return {"status": "skipped", "reason": "fetched at the start of the hour"}
    today = now_utc.astimezone(timezone.utc).date()
    availability = firms.fetch_availability(client, settings.firms_key)
    cells = firms.fetch_cells(client, settings.firms_key, today - timedelta(days=1), today, availability)
    return {"status": "ok", "cells": store.upsert_fire_cells(cells)}
```

`pipeline/myhaze/jobs/backfill.py`:

```python
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
```

In `.github/workflows/archive.yml`, add to the Archive step's `env:` block:

```yaml
          FIRMS_MAP_KEY: ${{ secrets.FIRMS_MAP_KEY }}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory pipeline run python -m myhaze.migrate && uv --directory pipeline run pytest -m "integration or not integration" -q 2>&1 | tail -2`
Expected: `applied: 0002_fires.sql`, then all tests pass (55 from Plan 1 + 12 geo + 7 firms + 1 http + 2 archive + 1 integration = 78 passed).

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add -A pipeline supabase .github
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): FIRMS fire hotspots on a 0.25-degree grid, hourly step and backfill

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Backfill fires and set the secret (needs the owner's FIRMS key in `.env`)**

```bash
grep -c '^FIRMS_MAP_KEY=.' "/Users/ryanchuah/Claude Code/MYHaze/.env"
uv --directory pipeline run python -m myhaze.jobs.backfill fires --start 2026-06-28
cd "/Users/ryanchuah/Claude Code/MYHaze" && grep '^FIRMS_MAP_KEY=' .env | cut -d= -f2- | tr -d '\n' | gh secret set FIRMS_MAP_KEY -R kiizenitc/myhaze
```

Expected: `1`. Then progress lines ending in `{'cells': N}` with N in the thousands. The fire season makes N large and the dry spell makes it small; both are fine. Then the secret is set. If the key isn't there yet, ledger it and carry on: Tasks 2–4 don't need it, and Task 5's features treat missing fire days as zero fire.

---

### Task 2: Unit conversions and calibration

**Files:**
- Create: `pipeline/myhaze/convert.py`, `pipeline/myhaze/calibration.py`, `pipeline/myhaze/calibration.json`, `pipeline/myhaze/jobs/calibrate.py`, `pipeline/tests/test_convert.py`, `pipeline/tests/test_calibration.py`
- Modify: `pipeline/myhaze/store.py` (+`hourly_series`), `pipeline/tests/test_store_integration.py`

**Interfaces:**
- Produces:
  - `convert.BANDS`
  - `convert.band(api: float) -> str`
  - `convert.US_TABLES: dict[str, tuple]`, keys `"us_epa_2012" | "us_epa_2024"`
  - `convert.MY_TABLES: dict[str, tuple]`, keys `"maaqs2020" | "modified_epa" | "us_epa_2012" | "us_epa_2024"`
  - `convert.index_from_conc(conc, table) -> float`
  - `convert.conc_from_index(index, table) -> float`
  - `convert.load_calibration(path=CALIBRATION_FILE) -> dict` (`{"aqicn_table", "my_table"}`)
  - Convenience converters that use the committed calibration:
    - `convert.aqicn_aqi_to_ugm3(aqi) -> float`
    - `convert.ugm3_to_api(conc) -> float`
    - `convert.api_to_ugm3(api) -> float`
  - `calibration.calibrate(aqicn_hourly: dict[str, dict[datetime, float]], doe_api: dict[str, dict[datetime, float]], min_hours=20, min_pairs=200) -> dict`, with keys `aqicn_table`, `my_table`, `mae`, `n` and `scores`.
  - `Store.hourly_series(source: str, column: str, since: datetime, param_symbol: str | None = None) -> dict[str, dict[datetime, float]]`
  - CLI: `python -m myhaze.jobs.calibrate` (writes `pipeline/myhaze/calibration.json`)

- [ ] **Step 1: Write the failing tests**

`pipeline/tests/test_convert.py`:

```python
import pytest

from myhaze import convert
from myhaze.convert import MY_TABLES, US_TABLES, band, conc_from_index, index_from_conc


@pytest.mark.parametrize("api,expected", [(0, "good"), (50, "good"), (51, "moderate"), (100, "moderate"),
                                          (101, "unhealthy"), (200, "unhealthy"), (201, "very_unhealthy"),
                                          (300, "very_unhealthy"), (301, "hazardous"), (999, "hazardous")])
def test_band_edges(api, expected):
    assert band(api) == expected


def test_band_rounds_before_comparing():
    assert band(100.4) == "moderate" and band(100.6) == "unhealthy"


@pytest.mark.parametrize("table,conc,index", [
    ("us_epa_2024", 9.0, 50), ("us_epa_2024", 35.4, 100), ("us_epa_2024", 55.5, 151), ("us_epa_2024", 125.4, 200),
    ("us_epa_2012", 12.0, 50), ("us_epa_2012", 150.4, 200),
])
def test_us_tables(table, conc, index):
    assert index_from_conc(conc, US_TABLES[table]) == pytest.approx(index, abs=0.01)


def test_my_maaqs_table_points():
    table = MY_TABLES["maaqs2020"]
    assert index_from_conc(15, table) == pytest.approx(50)
    assert index_from_conc(35, table) == pytest.approx(100)
    assert index_from_conc(75, table) == pytest.approx(200)


@pytest.mark.parametrize("name", sorted(MY_TABLES))
def test_round_trip_and_edges(name):
    table = MY_TABLES[name]
    for conc in (0.0, 5.0, 40.0, 140.0, 400.0):
        assert conc_from_index(index_from_conc(conc, table), table) == pytest.approx(conc, abs=1e-6)
    assert index_from_conc(-3, table) == 0
    assert index_from_conc(900, table) > 500  # extrapolates above the table, never crashes


def test_load_calibration_defaults_when_file_missing(tmp_path):
    assert convert.load_calibration(tmp_path / "missing.json") == {"aqicn_table": "us_epa_2024", "my_table": "maaqs2020"}


def test_load_calibration_ignores_unknown_table_names(tmp_path):
    path = tmp_path / "cal.json"
    path.write_text('{"aqicn_table": "nope", "my_table": "modified_epa"}')
    assert convert.load_calibration(path) == {"aqicn_table": "us_epa_2024", "my_table": "modified_epa"}
```

`pipeline/tests/test_calibration.py`:

```python
import math
from datetime import datetime, timedelta, timezone

import pytest

from myhaze.calibration import calibrate
from myhaze.convert import MY_TABLES, US_TABLES, index_from_conc

START = datetime(2026, 10, 15, tzinfo=timezone.utc)


def synthetic(hours=96, stations=4, us="us_epa_2024", my="maaqs2020"):
    aqicn, doe = {}, {}
    for s in range(stations):
        conc = {START + timedelta(hours=h): 30 + 60 * (1 + math.sin(h / 7 + s)) for h in range(hours)}
        aqicn[f"S{s}"] = {t: round(index_from_conc(c, US_TABLES[us])) for t, c in conc.items()}
        doe[f"S{s}"] = {}
        for h in range(23, hours):
            t = START + timedelta(hours=h)
            mean24 = sum(conc[t - timedelta(hours=k)] for k in range(24)) / 24
            doe[f"S{s}"][t] = round(index_from_conc(mean24, MY_TABLES[my]))
    return aqicn, doe


@pytest.mark.parametrize("us,my", [("us_epa_2024", "maaqs2020"), ("us_epa_2012", "modified_epa")])
def test_calibrate_recovers_the_tables_that_generated_the_data(us, my):
    aqicn, doe = synthetic(us=us, my=my)
    result = calibrate(aqicn, doe)
    assert (result["aqicn_table"], result["my_table"]) == (us, my)
    assert result["mae"] < 2.0 and result["n"] >= 200


def test_calibrate_refuses_too_little_data():
    aqicn, doe = synthetic(hours=30, stations=1)
    with pytest.raises(ValueError):
        calibrate(aqicn, doe)
```

Append to `pipeline/tests/test_store_integration.py`:

```python
def test_hourly_series_filters_by_source_and_symbol(store):
    recent = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    store.upsert_obs([Obs(TEST_ID, recent, "doe", api=120, param_symbol="**"),
                      Obs(TEST_ID, recent - timedelta(hours=1), "doe", api=40, param_symbol="c"),
                      Obs(TEST_ID, recent, "aqicn", api=120, pm25_aqi=150)])
    since = recent - timedelta(hours=5)
    assert store.hourly_series("doe", "api", since, param_symbol="**")[TEST_ID] == {recent: 120.0}
    assert store.hourly_series("aqicn", "pm25_aqi", since)[TEST_ID] == {recent: 150.0}
```

Also change that file's datetime import to `from datetime import datetime, timedelta, timezone`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest -q 2>&1 | tail -3`
Expected: FAIL. Collection errors for `myhaze.convert` and `myhaze.calibration`.

- [ ] **Step 3: Write the implementation**

`pipeline/myhaze/convert.py`:

```python
"""PM2.5 unit conversions: US AQI (what aqicn publishes) <-> µg/m³ <-> Malaysian API (DOE's scale).

DOE does not publish its PM2.5 breakpoints online, so the table actually used is chosen by
`python -m myhaze.jobs.calibrate` from archived DOE readings and stored in calibration.json.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

BANDS = (("good", 50), ("moderate", 100), ("unhealthy", 200), ("very_unhealthy", 300), ("hazardous", math.inf))

# (concentration low, concentration high, index low, index high)
US_EPA_2012 = ((0.0, 12.0, 0, 50), (12.1, 35.4, 51, 100), (35.5, 55.4, 101, 150), (55.5, 150.4, 151, 200),
               (150.5, 250.4, 201, 300), (250.5, 350.4, 301, 400), (350.5, 500.4, 401, 500))
US_EPA_2024 = ((0.0, 9.0, 0, 50), (9.1, 35.4, 51, 100), (35.5, 55.4, 101, 150), (55.5, 125.4, 151, 200),
               (125.5, 225.4, 201, 300), (225.5, 325.4, 301, 500))
US_TABLES = {"us_epa_2012": US_EPA_2012, "us_epa_2024": US_EPA_2024}
MY_TABLES = {
    "maaqs2020": ((0, 15, 0, 50), (15, 35, 50, 100), (35, 75, 100, 200), (75, 250, 200, 300), (250, 500, 300, 500)),
    "modified_epa": ((0.0, 12.0, 0, 50), (12.1, 50.4, 51, 100), (50.5, 55.4, 101, 150), (55.5, 150.4, 151, 200),
                     (150.5, 250.4, 201, 300), (250.5, 350.4, 301, 400), (350.5, 500.4, 401, 500)),
    "us_epa_2012": US_EPA_2012,
    "us_epa_2024": US_EPA_2024,
}
DEFAULTS = {"aqicn_table": "us_epa_2024", "my_table": "maaqs2020"}
CALIBRATION_FILE = Path(__file__).with_name("calibration.json")


def band(api: float) -> str:
    value = round(api)
    return next(name for name, upper in BANDS if value <= upper)


@lru_cache(maxsize=None)
def _knots(table: tuple) -> tuple[tuple[float, float], ...]:
    points = set()
    for c_lo, c_hi, i_lo, i_hi in table:
        points.add((float(c_lo), float(i_lo)))
        points.add((float(c_hi), float(i_hi)))
    return tuple(sorted(points))


def _interp(x: float, points) -> float:
    x = max(float(x), 0.0)
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x <= x1:
            return y1 if x1 == x0 else y0 + (x - x0) * (y1 - y0) / (x1 - x0)
    (x0, y0), (x1, y1) = points[-2], points[-1]
    return y1 + (x - x1) * (y1 - y0) / (x1 - x0)


def index_from_conc(conc: float, table: tuple) -> float:
    return _interp(conc, _knots(table))


def conc_from_index(index: float, table: tuple) -> float:
    return _interp(index, tuple((i, c) for c, i in _knots(table)))


def load_calibration(path: Path = CALIBRATION_FILE) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {
        "aqicn_table": data.get("aqicn_table") if data.get("aqicn_table") in US_TABLES else DEFAULTS["aqicn_table"],
        "my_table": data.get("my_table") if data.get("my_table") in MY_TABLES else DEFAULTS["my_table"],
    }


_CALIBRATION = load_calibration()


def aqicn_aqi_to_ugm3(aqi: float) -> float:
    return conc_from_index(aqi, US_TABLES[_CALIBRATION["aqicn_table"]])


def ugm3_to_api(conc: float) -> float:
    return index_from_conc(conc, MY_TABLES[_CALIBRATION["my_table"]])


def api_to_ugm3(api: float) -> float:
    return conc_from_index(api, MY_TABLES[_CALIBRATION["my_table"]])
```

`pipeline/myhaze/calibration.json`:

```json
{
  "aqicn_table": "us_epa_2024",
  "my_table": "maaqs2020",
  "status": "uncalibrated defaults; run python -m myhaze.jobs.calibrate once 24 hours of aqicn hourly data exist"
}
```

`pipeline/myhaze/calibration.py`:

```python
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
```

Append to `Store` in `pipeline/myhaze/store.py`:

```python
    _SERIES_COLUMNS = {"api", "pm25_aqi", "pm10_aqi"}

    def hourly_series(self, source: str, column: str, since: datetime,
                      param_symbol: str | None = None) -> dict[str, dict[datetime, float]]:
        if column not in self._SERIES_COLUMNS:
            raise ValueError(f"unsupported column {column!r}")
        sql = (f"select station_id, hour, {column} from obs_hourly "
               f"where source = %s and hour >= %s and {column} is not null")
        params: list = [source, since]
        if param_symbol is not None:
            sql += " and param_symbol = %s"
            params.append(param_symbol)
        series: dict[str, dict[datetime, float]] = {}
        for station_id, hour, value in self.conn.execute(sql, params).fetchall():
            series.setdefault(station_id, {})[hour] = float(value)
        return series
```

`pipeline/myhaze/jobs/calibrate.py`:

```python
"""Choose the PM2.5 conversion tables from archived data and write calibration.json."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

from ..calibration import calibrate
from ..config import load_settings
from ..convert import CALIBRATION_FILE
from ..store import Store


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    if not settings.db_url:
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 2
    store = Store.connect(settings.db_url)
    try:
        since = datetime.now(timezone.utc) - timedelta(days=14)
        aqicn = store.hourly_series("aqicn", "pm25_aqi", since)
        doe = store.hourly_series("doe", "api", since, param_symbol="**")
    finally:
        store.close()
    try:
        result = calibrate(aqicn, doe)
    except ValueError as exc:
        print(f"calibration not possible yet: {exc}", file=sys.stderr)
        return 1
    result["computed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result["status"] = "calibrated"
    CALIBRATION_FILE.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory pipeline run pytest -m "integration or not integration" -q 2>&1 | tail -2`
Expected: all pass (78 + 24 convert + 3 calibration + 1 integration = 106 passed).

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add -A pipeline
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): PM2.5 unit conversions with data-driven table calibration

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Calibrate on real data (needs 24+ hours of archive, from about 10:00 MYT on Friday 16 October)**

```bash
uv --directory pipeline run python -m myhaze.jobs.calibrate
```

Expected: JSON naming the winning tables, `n` ≥ 200, and an `mae` that is **small (≤ 5 API points)**. If the best MAE is larger, none of the candidate tables matches DOE. Then:
- Ledger a ruling.
- Keep the best pair.
- Add a note to the About page in Plan 3 that the conversion is approximate.

If it exits with "not possible yet", re-run once enough hours exist. The committed defaults keep everything working meanwhile.

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add pipeline/myhaze/calibration.json
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "chore: calibrate PM2.5 conversion tables from archived DOE data

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Daily PM2.5 history (aqicn CSV exports and archive daily means)

**Files:**
- Create: `pipeline/myhaze/sources/aqicn_csv.py`, `pipeline/myhaze/daily.py`, `pipeline/myhaze/jobs/load_daily.py`, `supabase/migrations/0003_daily.sql`, `pipeline/tests/test_aqicn_csv.py`, `pipeline/tests/test_daily.py`
- Modify: `pipeline/myhaze/store.py`, `pipeline/tests/test_store_integration.py`

**Interfaces:**
- Consumes:
  - `convert.aqicn_aqi_to_ugm3`
  - `Store.hourly_series`
  - `config.MYT`
- Produces:
  - `aqicn_csv.parse_daily_csv(text) -> list[tuple[date, float]]`, returning `(day, pm25 US AQI)` sorted by day
  - `daily.daily_means(series: dict[datetime, float], min_hours=18) -> dict[date, float]` (Malaysia days)
  - `daily.trailing_mean(series, end_hour: datetime, hours=24, min_hours=18) -> float | None`
  - `Store.upsert_daily_pm25(rows: list[tuple[str, date, float, str]]) -> int`, where source is `'aqicn_csv' | 'archive'`
  - `Store.daily_pm25(start: date, end: date) -> dict[tuple[str, date], float]`, which prefers `archive` over `aqicn_csv`
  - `load_daily.load_csv_dir(store, directory, since=HISTORY_START) -> dict`
  - `load_daily.refresh_archive_daily(store, today: date) -> dict`
  - CLI: `python -m myhaze.jobs.load_daily [--dir PATH]`

- [ ] **Step 1: Write the failing tests**

`pipeline/tests/test_aqicn_csv.py`:

```python
from datetime import date

import pytest

from myhaze.sources.aqicn_csv import parse_daily_csv

EXPORT = (
    "date, pm25, pm10, o3, no2, so2, co\n"
    "2026/10/14, 172, 52, 3, 8, 2, 1\n"
    "2026/7/1, 61, 30, , 5, 1, \n"
    "2026-09-30, , 40, 2, 4, 1, 1\n"
    "garbage, 10\n"
    "2026/10/13,  159 , 48, 3, 7, 2, 1\n"
)


def test_parse_daily_csv_handles_spaces_dates_and_blanks():
    assert parse_daily_csv(EXPORT) == [(date(2026, 7, 1), 61.0), (date(2026, 10, 13), 159.0),
                                       (date(2026, 10, 14), 172.0)]


def test_parse_daily_csv_requires_the_pm25_column():
    with pytest.raises(ValueError):
        parse_daily_csv("date, pm10\n2026/10/14, 52\n")


def test_parse_daily_csv_of_empty_text_is_empty():
    assert parse_daily_csv("") == []
```

`pipeline/tests/test_daily.py`:

```python
from datetime import date, datetime, timedelta, timezone

from myhaze.daily import daily_means, trailing_mean

# 2026-10-14 00:00 MYT is 2026-10-13 16:00 UTC
MYT_MIDNIGHT = datetime(2026, 10, 13, 16, tzinfo=timezone.utc)


def test_daily_means_use_malaysia_days_and_need_18_hours():
    series = {MYT_MIDNIGHT + timedelta(hours=h): 10.0 + (h // 24) * 10 for h in range(24 + 17)}
    assert daily_means(series) == {date(2026, 10, 14): 10.0}


def test_trailing_mean_needs_enough_hours():
    end = MYT_MIDNIGHT + timedelta(hours=30)
    series = {end - timedelta(hours=k): float(k) for k in range(24)}
    assert trailing_mean(series, end) == sum(range(24)) / 24
    assert trailing_mean({end: 5.0}, end) is None
```

Append to `pipeline/tests/test_store_integration.py`:

```python
def test_daily_pm25_prefers_archive_over_csv(store):
    from datetime import date

    day = date(1999, 1, 2)
    store.upsert_daily_pm25([(TEST_ID, day, 40.0, "aqicn_csv"), (TEST_ID, day, 42.5, "archive"),
                             (TEST_ID, date(1999, 1, 3), 50.0, "aqicn_csv")])
    try:
        got = store.daily_pm25(day, date(1999, 1, 3))
        assert got[(TEST_ID, day)] == 42.5 and got[(TEST_ID, date(1999, 1, 3))] == 50.0
    finally:
        store.conn.execute("delete from daily_pm25 where station_id = %s", (TEST_ID,))
```

In the fixture's teardown loop, add `"daily_pm25"` to the tuple of tables cleaned *before* `"stations"`: `("obs_hourly", "cams_fcst", "daily_pm25", "stations")`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest -q 2>&1 | tail -3`
Expected: FAIL. Collection errors for `myhaze.sources.aqicn_csv` and `myhaze.daily`.

- [ ] **Step 3: Write the implementation**

`pipeline/myhaze/sources/aqicn_csv.py`:

```python
"""Parser for aqicn's per-station "Download this data (CSV format)" export (daily values, US AQI)."""
from __future__ import annotations

import csv
import io
import math
from datetime import date, datetime


def parse_daily_csv(text: str) -> list[tuple[date, float]]:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    header = [cell.strip().lower() for cell in rows[0]]
    if "date" not in header or "pm25" not in header:
        raise ValueError("aqicn CSV needs 'date' and 'pm25' columns")
    date_col, pm25_col = header.index("date"), header.index("pm25")
    values: dict[date, float] = {}
    for row in rows[1:]:
        if len(row) <= max(date_col, pm25_col):
            continue
        try:
            day = datetime.strptime(row[date_col].strip().replace("-", "/"), "%Y/%m/%d").date()
            value = float(row[pm25_col].strip())
        except ValueError:
            continue
        if math.isfinite(value) and value >= 0:
            values[day] = value
    return sorted(values.items())
```

`pipeline/myhaze/daily.py`:

```python
"""Daily and trailing means of hourly series, on Malaysia calendar days."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from .config import MYT


def daily_means(series: dict[datetime, float], min_hours: int = 18) -> dict[date, float]:
    by_day: dict[date, list[float]] = defaultdict(list)
    for hour, value in series.items():
        by_day[hour.astimezone(MYT).date()].append(value)
    return {day: sum(v) / len(v) for day, v in by_day.items() if len(v) >= min_hours}


def trailing_mean(series: dict[datetime, float], end_hour: datetime, hours: int = 24,
                  min_hours: int = 18) -> float | None:
    values = [series[t] for t in (end_hour - timedelta(hours=k) for k in range(hours)) if t in series]
    return sum(values) / len(values) if len(values) >= min_hours else None
```

`supabase/migrations/0003_daily.sql`:

```sql
-- Daily-mean PM2.5 (µg/m³) per station and Malaysia calendar day: the training target and persistence input.
-- 'aqicn_csv' rows come from the owner's one-time exports; 'archive' rows from our own hourly archive.
create table daily_pm25 (
  station_id text not null references stations (station_id),
  day date not null,
  pm25_ugm3 real not null,
  source text not null check (source in ('aqicn_csv', 'archive')),
  primary key (station_id, day, source)
);
alter table daily_pm25 enable row level security;
```

Append to `Store`:

```python
    def upsert_daily_pm25(self, rows: list[tuple[str, date, float, str]]) -> int:
        known = self._known_ids()
        keep = [r for r in rows if r[0] in known]
        if keep:
            with self.conn.transaction(), self.conn.cursor() as cur:
                cur.executemany(
                    "insert into daily_pm25 (station_id, day, pm25_ugm3, source) values (%s, %s, %s, %s) "
                    "on conflict (station_id, day, source) do update set pm25_ugm3 = excluded.pm25_ugm3", keep)
        return len(keep)

    def daily_pm25(self, start: date, end: date) -> dict[tuple[str, date], float]:
        rows = self.conn.execute(
            "select distinct on (station_id, day) station_id, day, pm25_ugm3 from daily_pm25 "
            "where day between %s and %s order by station_id, day, (source = 'archive') desc",
            (start, end)).fetchall()
        return {(station_id, day): float(value) for station_id, day, value in rows}
```

`pipeline/myhaze/jobs/load_daily.py`:

```python
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
from ..store import Store

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
    store = Store.connect(settings.db_url)
    try:
        print(load_csv_dir(store, args.dir))
        print(refresh_archive_daily(store, datetime.now(MYT).date()))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory pipeline run python -m myhaze.migrate && uv --directory pipeline run pytest -m "integration or not integration" -q 2>&1 | tail -2`
Expected: `applied: 0003_daily.sql`, then all pass (106 + 3 aqicn_csv + 2 daily + 1 integration = 112 passed).

- [ ] **Step 5: Check the real export format, then load whatever exports exist**

```bash
ls "/Users/ryanchuah/Claude Code/MYHaze/data/raw/aqicn_daily" | head -3
f=$(ls "/Users/ryanchuah/Claude Code/MYHaze/data/raw/aqicn_daily"/*.csv 2>/dev/null | head -1); [ -n "$f" ] && head -4 "$f"
uv --directory pipeline run python -m myhaze.jobs.load_daily
```

Expected: the first lines show a `date` column and a `pm25` column. **If the real header or date format differs from the test fixture:**
1. Copy two real lines into `EXPORT` (only dates and numbers; nothing secret).
2. Adjust `parse_daily_csv` until the tests pass.
3. Ledger it as a ruling.

The loader prints `{'files': N, 'rows': M, ...}`. Before the exports arrive, `files=0` is expected; just re-run later. `unknown_files` must be empty, otherwise a file name isn't a DOE id.

- [ ] **Step 6: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add -A pipeline supabase
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): daily PM2.5 history from aqicn exports and the hourly archive

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 4: Weather and CAMS history (Open-Meteo) and live weather

**Files:**
- Create: `pipeline/myhaze/weather.py`, `supabase/migrations/0004_weather.sql`, `pipeline/tests/test_weather.py`
- Modify: `pipeline/myhaze/rows.py`, `pipeline/myhaze/sources/openmeteo.py`, `pipeline/myhaze/store.py`, `pipeline/myhaze/jobs/backfill.py`, `pipeline/tests/test_openmeteo.py`, `pipeline/tests/test_store_integration.py`

**Interfaces:**
- Consumes:
  - `daily.daily_means`
  - `openmeteo.AQ_URL`, `BATCH`, `_value`
  - `backfill.BACKFILLS`
- Produces:
  - `rows.HourlyWeather(station_id, times, precip, blh, wind10, wind120, wind120_from, rh)` (UTC hours; lists may hold None)
  - `openmeteo.parse_weather(payload, points, suffix="") -> list[HourlyWeather]`
  - `openmeteo.fetch_weather_forecast(client, points, days=3) -> list[HourlyWeather]` (includes the past day and mixing height)
  - `openmeteo.fetch_previous_runs(client, points, start: date, end: date, lead: int) -> list[HourlyWeather]` (no mixing height)
  - `openmeteo.fetch_cams_hourly_history(client, stations, start, end) -> dict[str, dict[datetime, float]]`
  - `weather.RAIN_POINTS: tuple[Station, ...]` (ids `R:<name>`)
  - `weather.WeatherDay(precip_mm, wet_hours, wind10_kmh, wind120_kmh, wind120_from_deg, rh_mean)`
  - `weather.circular_mean_deg(directions, weights) -> float | None`
  - `weather.daily_weather(hw, min_hours=18) -> dict[date, WeatherDay]` (Malaysia days)
  - `Store.upsert_weather_daily(rows: list[tuple[str, date, int, WeatherDay]]) -> int`
  - `Store.weather_daily(start, end) -> dict[tuple[str, date, int], WeatherDay]`
  - `Store.save_weather_latest(items: list[HourlyWeather], issued_at: datetime) -> int`
  - `Store.weather_latest() -> tuple[datetime | None, dict[str, HourlyWeather]]`
  - `Store.upsert_cams_daily(rows: list[tuple[str, date, float]]) -> int`
  - `Store.cams_daily(start, end) -> dict[tuple[str, date], float]`
  - `Store.latest_cams() -> dict[str, CamsForecast]`
  - `Store.max_day(table: str) -> date | None`
  - `backfill.BACKFILLS["weather"]`, `backfill.BACKFILLS["cams"]`

- [ ] **Step 1: Write the failing tests**

Append to `pipeline/tests/test_openmeteo.py`:

```python
from datetime import date

WEATHER_TWO = [
    {"hourly": {"time": ["2026-10-15T00:00", "2026-10-15T01:00"],
                "precipitation_previous_day1": [0.0, 1.2], "wind_speed_10m_previous_day1": [5.0, 6.0],
                "wind_speed_120m_previous_day1": [12.0, 14.0], "wind_direction_120m_previous_day1": [200, 210],
                "relative_humidity_2m_previous_day1": [80, 85]}},
    {"hourly": {"time": ["2026-10-15T00:00", "2026-10-15T01:00"],
                "precipitation_previous_day1": [None, 0.0], "wind_speed_10m_previous_day1": [3.0, 3.0],
                "wind_speed_120m_previous_day1": [9.0, 9.0], "wind_direction_120m_previous_day1": [90, 95],
                "relative_humidity_2m_previous_day1": [70, 72]}},
]


def test_parse_weather_reads_suffixed_columns_and_marks_missing_ones():
    got = openmeteo.parse_weather(WEATHER_TWO, STATIONS, "_previous_day1")
    assert got[0].times[1] == datetime(2026, 10, 15, 1, tzinfo=timezone.utc)
    assert (got[0].precip, got[0].wind120_from, got[1].precip) == ([0.0, 1.2], [200.0, 210.0], [None, 0.0])
    assert got[0].blh == [None, None]


def test_parse_weather_rejects_a_location_count_mismatch():
    with pytest.raises(FetchError):
        openmeteo.parse_weather(WEATHER_TWO, STATIONS[:1])


def test_fetch_previous_runs_asks_for_the_lead_suffix_and_dates():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=WEATHER_TWO)

    got = openmeteo.fetch_previous_runs(make_client(transport=httpx.MockTransport(handler)), STATIONS,
                                        date(2026, 7, 1), date(2026, 7, 3), lead=1)
    assert len(got) == 2
    assert "wind_direction_120m_previous_day1" in seen[0]["hourly"].split(",")
    assert (seen[0]["start_date"], seen[0]["end_date"]) == ("2026-06-30", "2026-07-03")


def test_fetch_cams_hourly_history_returns_series_per_station():
    def handler(request):
        return httpx.Response(200, json=fixtures.CAMS_TWO_STATIONS)

    got = openmeteo.fetch_cams_hourly_history(make_client(transport=httpx.MockTransport(handler)), STATIONS,
                                              date(2026, 10, 15), date(2026, 10, 15))
    assert got["CA01R"] == {SLOT: 20.1, SLOT.replace(hour=2): 22.5}
```

`pipeline/tests/test_weather.py`:

```python
from datetime import date, datetime, timedelta, timezone

import pytest

from myhaze.rows import HourlyWeather
from myhaze.weather import circular_mean_deg, daily_weather

MYT_MIDNIGHT = datetime(2026, 10, 13, 16, tzinfo=timezone.utc)  # 00:00 MYT on 14 Oct


def test_daily_weather_sums_rain_counts_wet_hours_and_averages_wind():
    times = [MYT_MIDNIGHT + timedelta(hours=h) for h in range(24)]
    hw = HourlyWeather("S", times, precip=[1.0 if h < 3 else 0.0 for h in range(24)], blh=[None] * 24,
                       wind10=[4.0] * 24, wind120=[10.0] * 24, wind120_from=[350.0 if h % 2 else 10.0 for h in range(24)],
                       rh=[80.0] * 24)
    day = daily_weather(hw)[date(2026, 10, 14)]
    assert (day.precip_mm, day.wet_hours, day.wind10_kmh, day.rh_mean) == (3.0, 3, 4.0, 80.0)
    assert day.wind120_from_deg == pytest.approx(0.0, abs=0.01) or day.wind120_from_deg == pytest.approx(360.0, abs=0.01)


def test_daily_weather_skips_days_with_too_few_hours():
    times = [MYT_MIDNIGHT + timedelta(hours=h) for h in range(10)]
    hw = HourlyWeather("S", times, [0.0] * 10, [None] * 10, [1.0] * 10, [1.0] * 10, [90.0] * 10, [50.0] * 10)
    assert daily_weather(hw) == {}


def test_circular_mean_handles_missing_and_calm():
    assert circular_mean_deg([90, None, 90], [5, 5, None]) == pytest.approx(90.0)
    assert circular_mean_deg([None], [1]) is None
```

Append to `pipeline/tests/test_store_integration.py`:

```python
def test_weather_tables_roundtrip(store):
    from datetime import date

    from myhaze.rows import HourlyWeather
    from myhaze.weather import WeatherDay

    day = date(1999, 1, 4)
    wd = WeatherDay(2.5, 3, 4.0, 12.0, 225.0, 80.0)
    hour = datetime(1999, 1, 4, tzinfo=timezone.utc)
    hw = HourlyWeather("ZZTEST", [hour, hour + timedelta(hours=1)], [0.0, None], [300.0, 250.0], [1.0, 2.0],
                       [5.0, 6.0], [200.0, 210.0], [70.0, 75.0])
    try:
        store.upsert_weather_daily([("ZZTEST", day, 1, wd)])
        assert store.weather_daily(day, day) == {("ZZTEST", day, 1): wd}
        store.save_weather_latest([hw], hour)
        issued, latest = store.weather_latest()
        assert issued == hour and latest["ZZTEST"] == hw
    finally:
        store.conn.execute("delete from weather_daily where station_id = 'ZZTEST'")
        store.conn.execute("delete from weather_latest where station_id = 'ZZTEST'")


def test_cams_daily_and_latest_cams(store):
    from datetime import date

    store.upsert_cams_daily([(TEST_ID, date(1999, 1, 5), 33.3), ("NOPE1", date(1999, 1, 5), 1.0)])
    slot = datetime(1999, 1, 5, 6, tzinfo=timezone.utc)
    store.upsert_cams([CamsForecast(TEST_ID, slot, slot, [10.0, 11.0])])
    try:
        assert store.cams_daily(date(1999, 1, 5), date(1999, 1, 5)) == {(TEST_ID, date(1999, 1, 5)): pytest.approx(33.3)}
        assert store.latest_cams()[TEST_ID].pm25 == [10.0, 11.0]
        assert store.max_day("cams_daily") is not None
    finally:
        store.conn.execute("delete from cams_daily where station_id = %s", (TEST_ID,))
```

Add `"cams_daily"` to the fixture's teardown tuple, before `"stations"`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest -q 2>&1 | tail -3`
Expected: FAIL. A collection error for `myhaze.weather`, and `AttributeError` for the new `openmeteo` functions.

- [ ] **Step 3: Write the implementation**

Append to `pipeline/myhaze/rows.py`:

```python
@dataclass(frozen=True)
class HourlyWeather:
    """Hourly weather at a point. `times` are UTC hours; any value may be None."""
    station_id: str
    times: list[datetime]
    precip: list[float | None]
    blh: list[float | None]
    wind10: list[float | None]
    wind120: list[float | None]
    wind120_from: list[float | None]
    rh: list[float | None]
```

Append to `pipeline/myhaze/sources/openmeteo.py` (add `HourlyWeather` to the rows import and `date` to the datetime import):

```python
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
# Everything the archive of past forecasts can supply; mixing height is live-forecast only.
WEATHER_VARS = ("precipitation", "wind_speed_10m", "wind_speed_120m", "wind_direction_120m", "relative_humidity_2m")


def _items(payload, points: list[Station]) -> list:
    items = payload if isinstance(payload, list) else [payload]
    if len(items) != len(points):
        raise FetchError(f"Open-Meteo returned {len(items)} locations for {len(points)} points")
    return items


def parse_weather(payload, points: list[Station], suffix: str = "") -> list[HourlyWeather]:
    weather = []
    for point, item in zip(points, _items(payload, points)):
        hourly = item.get("hourly") if isinstance(item, dict) else None
        if not isinstance(hourly, dict) or not isinstance(hourly.get("time"), list):
            continue
        try:
            times = [datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in hourly["time"]]
        except (TypeError, ValueError):
            continue

        def column(name: str) -> list[float | None]:
            values = hourly.get(name + suffix)
            if isinstance(values, list) and len(values) == len(times):
                return [_value(v) for v in values]
            return [None] * len(times)

        weather.append(HourlyWeather(point.station_id, times, column("precipitation"), column("boundary_layer_height"),
                                     column("wind_speed_10m"), column("wind_speed_120m"),
                                     column("wind_direction_120m"), column("relative_humidity_2m")))
    return weather


def _batched_weather(client: httpx.Client, url: str, points: list[Station], params: dict, label: str,
                     suffix: str = "") -> list[HourlyWeather]:
    weather = []
    for start in range(0, len(points), BATCH):
        chunk = points[start:start + BATCH]
        payload = get_json(client, url, params=dict(params, latitude=",".join(f"{p.lat:.4f}" for p in chunk),
                                                     longitude=",".join(f"{p.lon:.4f}" for p in chunk)), label=label)
        weather.extend(parse_weather(payload, chunk, suffix))
    return weather


def fetch_weather_forecast(client: httpx.Client, points: list[Station], days: int = 3) -> list[HourlyWeather]:
    hourly = ",".join(WEATHER_VARS + ("boundary_layer_height",))
    return _batched_weather(client, FORECAST_URL, points,
                            {"hourly": hourly, "forecast_days": days, "past_days": 1, "timezone": "GMT"},
                            "Open-Meteo forecast")


def fetch_previous_runs(client: httpx.Client, points: list[Station], start: date, end: date,
                        lead: int) -> list[HourlyWeather]:
    suffix = f"_previous_day{lead}"
    # One day earlier than `start` so the first Malaysia day (which begins 16:00 UTC the day before) is complete.
    return _batched_weather(client, PREVIOUS_RUNS_URL, points,
                            {"hourly": ",".join(v + suffix for v in WEATHER_VARS),
                             "start_date": (start - timedelta(days=1)).isoformat(), "end_date": end.isoformat(),
                             "timezone": "GMT"}, "Open-Meteo previous runs", suffix)


def fetch_cams_hourly_history(client: httpx.Client, stations: list[Station], start: date,
                              end: date) -> dict[str, dict[datetime, float]]:
    series: dict[str, dict[datetime, float]] = {}
    for first in range(0, len(stations), BATCH):
        chunk = stations[first:first + BATCH]
        payload = get_json(client, AQ_URL, params={
            "latitude": ",".join(f"{s.lat:.4f}" for s in chunk), "longitude": ",".join(f"{s.lon:.4f}" for s in chunk),
            "hourly": "pm2_5", "start_date": (start - timedelta(days=1)).isoformat(), "end_date": end.isoformat(),
            "timezone": "GMT"}, label="Open-Meteo air-quality history")
        for station, forecast in zip(chunk, parse_cams(payload, chunk, datetime.min.replace(tzinfo=timezone.utc))):
            series[station.station_id] = {forecast.first_valid + timedelta(hours=i): v
                                          for i, v in enumerate(forecast.pm25) if v is not None}
    return series
```

Also change the openmeteo imports to `from datetime import date, datetime, timedelta, timezone`.

`pipeline/myhaze/weather.py`:

```python
"""Daily weather summaries on Malaysia days, and the points whose rain matters for the fire regions."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from .config import MYT
from .rows import HourlyWeather, Station

WET_MM = 0.5
# Rain here suppresses the peat fires that send smoke to Malaysia.
RAIN_POINTS = (
    Station("R:riau", "Riau", "Indonesia", 0.5, 101.5),
    Station("R:jambi", "Jambi", "Indonesia", -1.6, 103.6),
    Station("R:south_sumatra", "South Sumatra", "Indonesia", -3.3, 104.9),
    Station("R:west_kalimantan", "West Kalimantan", "Indonesia", -0.1, 110.0),
    Station("R:central_kalimantan", "Central Kalimantan", "Indonesia", -1.7, 113.4),
    Station("R:south_kalimantan", "South Kalimantan", "Indonesia", -3.0, 115.3),
)


@dataclass(frozen=True)
class WeatherDay:
    precip_mm: float | None
    wet_hours: int | None
    wind10_kmh: float | None
    wind120_kmh: float | None
    wind120_from_deg: float | None
    rh_mean: float | None


def _mean(values) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 2) if present else None


def circular_mean_deg(directions, weights) -> float | None:
    x = y = 0.0
    seen = False
    for direction, weight in zip(directions, weights):
        if direction is None:
            continue
        w = 1.0 if weight is None else max(weight, 0.0)
        x += w * math.sin(math.radians(direction))
        y += w * math.cos(math.radians(direction))
        seen = True
    if not seen or (abs(x) < 1e-9 and abs(y) < 1e-9):
        return None
    return round((math.degrees(math.atan2(x, y)) + 360.0) % 360.0, 2)


def daily_weather(hw: HourlyWeather, min_hours: int = 18) -> dict[date, WeatherDay]:
    by_day: dict[date, list[int]] = defaultdict(list)
    for i, t in enumerate(hw.times):
        by_day[t.astimezone(MYT).date()].append(i)
    days = {}
    for day, idx in by_day.items():
        if len(idx) < min_hours:
            continue
        rain = [hw.precip[i] for i in idx if hw.precip[i] is not None]
        days[day] = WeatherDay(
            precip_mm=round(sum(rain), 2) if rain else None,
            wet_hours=sum(1 for v in rain if v >= WET_MM) if rain else None,
            wind10_kmh=_mean(hw.wind10[i] for i in idx),
            wind120_kmh=_mean(hw.wind120[i] for i in idx),
            wind120_from_deg=circular_mean_deg([hw.wind120_from[i] for i in idx], [hw.wind120[i] for i in idx]),
            rh_mean=_mean(hw.rh[i] for i in idx),
        )
    return days
```

`supabase/migrations/0004_weather.sql`:

```sql
-- Daily summaries of archived real forecasts (lead 1 = issued the day before, lead 2 = two days before),
-- the latest hourly forecast per point, and CAMS daily means for the corrected-CAMS baseline.
-- weather tables also hold fire-region rain points ('R:...'), so they have no station foreign key.
create table weather_daily (
  station_id text not null,
  day date not null,
  lead_days smallint not null check (lead_days between 1 and 2),
  precip_mm real,
  wet_hours smallint,
  wind10_kmh real,
  wind120_kmh real,
  wind120_from_deg real,
  rh_mean real,
  primary key (station_id, day, lead_days)
);

create table weather_latest (
  station_id text primary key,
  issued_at timestamptz not null,
  times timestamptz[] not null,
  precip real[] not null,
  blh real[] not null,
  wind10 real[] not null,
  wind120 real[] not null,
  wind120_from real[] not null,
  rh real[] not null
);

create table cams_daily (
  station_id text not null references stations (station_id),
  day date not null,
  pm25_ugm3 real not null,
  primary key (station_id, day)
);

alter table weather_daily enable row level security;
alter table weather_latest enable row level security;
alter table cams_daily enable row level security;
```

Append to `Store` (add `HourlyWeather` to the rows import; import `WeatherDay` with `from .weather import WeatherDay`):

```python
    _DAY_TABLES = {"weather_daily", "cams_daily", "daily_pm25", "fire_grid_daily"}

    def upsert_weather_daily(self, rows: list[tuple[str, date, int, WeatherDay]]) -> int:
        if rows:
            with self.conn.transaction(), self.conn.cursor() as cur:
                cur.executemany(
                    "insert into weather_daily (station_id, day, lead_days, precip_mm, wet_hours, wind10_kmh, "
                    "wind120_kmh, wind120_from_deg, rh_mean) values (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "on conflict (station_id, day, lead_days) do update set precip_mm = excluded.precip_mm, "
                    "wet_hours = excluded.wet_hours, wind10_kmh = excluded.wind10_kmh, "
                    "wind120_kmh = excluded.wind120_kmh, wind120_from_deg = excluded.wind120_from_deg, "
                    "rh_mean = excluded.rh_mean",
                    [(sid, day, lead, w.precip_mm, w.wet_hours, w.wind10_kmh, w.wind120_kmh, w.wind120_from_deg,
                      w.rh_mean) for sid, day, lead, w in rows])
        return len(rows)

    def weather_daily(self, start: date, end: date) -> dict[tuple[str, date, int], WeatherDay]:
        rows = self.conn.execute(
            "select station_id, day, lead_days, precip_mm, wet_hours, wind10_kmh, wind120_kmh, wind120_from_deg, "
            "rh_mean from weather_daily where day between %s and %s", (start, end)).fetchall()
        return {(sid, day, int(lead)): WeatherDay(*(None if v is None else (int(v) if i == 1 else float(v))
                                                     for i, v in enumerate(values)))
                for sid, day, lead, *values in rows}

    def save_weather_latest(self, items: list[HourlyWeather], issued_at: datetime) -> int:
        if items:
            with self.conn.transaction(), self.conn.cursor() as cur:
                cur.executemany(
                    "insert into weather_latest (station_id, issued_at, times, precip, blh, wind10, wind120, "
                    "wind120_from, rh) values (%s, %s, %s, %s, %s, %s, %s, %s, %s) on conflict (station_id) do update "
                    "set issued_at = excluded.issued_at, times = excluded.times, precip = excluded.precip, "
                    "blh = excluded.blh, wind10 = excluded.wind10, wind120 = excluded.wind120, "
                    "wind120_from = excluded.wind120_from, rh = excluded.rh",
                    [(w.station_id, issued_at, w.times, w.precip, w.blh, w.wind10, w.wind120, w.wind120_from, w.rh)
                     for w in items])
        return len(items)

    def weather_latest(self) -> tuple[datetime | None, dict[str, HourlyWeather]]:
        rows = self.conn.execute(
            "select station_id, issued_at, times, precip, blh, wind10, wind120, wind120_from, rh from weather_latest"
        ).fetchall()
        latest = {sid: HourlyWeather(sid, list(times), *[list(col) for col in cols])
                  for sid, _issued, times, *cols in rows}
        issued = min((r[1] for r in rows), default=None)
        return issued, latest

    def upsert_cams_daily(self, rows: list[tuple[str, date, float]]) -> int:
        known = self._known_ids()
        keep = [r for r in rows if r[0] in known]
        if keep:
            with self.conn.transaction(), self.conn.cursor() as cur:
                cur.executemany("insert into cams_daily (station_id, day, pm25_ugm3) values (%s, %s, %s) "
                                "on conflict (station_id, day) do update set pm25_ugm3 = excluded.pm25_ugm3", keep)
        return len(keep)

    def cams_daily(self, start: date, end: date) -> dict[tuple[str, date], float]:
        rows = self.conn.execute("select station_id, day, pm25_ugm3 from cams_daily where day between %s and %s",
                                 (start, end)).fetchall()
        return {(sid, day): float(v) for sid, day, v in rows}

    def latest_cams(self) -> dict[str, CamsForecast]:
        rows = self.conn.execute(
            "select distinct on (station_id) station_id, issued_slot, first_valid, pm25 from cams_fcst "
            "order by station_id, issued_slot desc").fetchall()
        return {sid: CamsForecast(sid, slot, first, list(values)) for sid, slot, first, values in rows}

    def max_day(self, table: str) -> date | None:
        if table not in self._DAY_TABLES:
            raise ValueError(f"unsupported table {table!r}")
        return self.conn.execute(f"select max(day) from {table}").fetchone()[0]
```

Append to `pipeline/myhaze/jobs/backfill.py` (add `from ..daily import daily_means`, `from ..sources import openmeteo`, `from ..weather import RAIN_POINTS, daily_weather`). Register the two new backfills in `BACKFILLS`:

```python
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
```

Delete the earlier one-entry `BACKFILLS = {"fires": backfill_fires}` line.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory pipeline run python -m myhaze.migrate && uv --directory pipeline run pytest -m "integration or not integration" -q 2>&1 | tail -2`
Expected: `applied: 0004_weather.sql`, then all pass (112 + 4 openmeteo + 3 weather + 2 integration = 121 passed).

- [ ] **Step 5: Backfill weather and CAMS history (no key needed)**

```bash
uv --directory pipeline run python -m myhaze.jobs.backfill weather --start 2026-06-28
uv --directory pipeline run python -m myhaze.jobs.backfill cams --start 2026-06-28
```

Expected:
- `{'weather_rows': N}` with N ≈ (68 + 6) points × ~110 days × 2 leads ≈ 16,000.
- `{'cams_rows': M}` with M ≈ 68 × 110 ≈ 7,500.

If Open-Meteo answers 429 (rate limit), wait 1 minute and re-run; upserts are idempotent.

- [ ] **Step 6: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add -A pipeline supabase
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): weather and CAMS history from Open-Meteo, daily weather summaries

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Shared feature builder (no hindsight)

**Files:**
- Create: `pipeline/myhaze/features.py`, `pipeline/tests/test_features.py`
- Modify: `pipeline/pyproject.toml` (+numpy, lightgbm), `pipeline/uv.lock`

**Interfaces:**
- Consumes:
  - `geo.region_of`
  - `firms.GRID_DEG`
  - `weather.RAIN_POINTS`, `WeatherDay`, `daily_weather`
  - `rows.FireCell`, `HourlyWeather`, `Station`
- Produces:
  - `features.FEATURES: tuple[str, ...]` (22 names, fixed order)
  - `features.MONOTONE: dict[str, int]`
  - `features.FIRE_REGIONS`, `features.REGION_GROUP`
  - `features.FeatureRow(station_id, issue_day, lead, target_day, x: dict, y: float | None, upwind_by_region: dict)`
  - `features.cell_arrays(cells) -> CellArrays | None`
  - `features.upwind_by_region(station, arrays, wind_from_deg) -> dict[str, float]`
  - `features.build_rows(stations, daily_pm, cells_by_day, weather, issue_days, leads=(1, 2)) -> list[FeatureRow]`
  - `features.live_weather_days(latest, issue, leads=(1, 2)) -> dict`
  - `features.build_live_rows(stations, now, pm_now, daily_pm, cells_by_day, weather_latest, leads=(1, 2)) -> list[FeatureRow]`

- [ ] **Step 1: Add the numerical dependencies**

```bash
cd "/Users/ryanchuah/Claude Code/MYHaze/pipeline" && uv add "numpy>=2.0,<3" "lightgbm>=4.6,<5" && brew list libomp >/dev/null 2>&1 || brew install libomp
uv --directory "/Users/ryanchuah/Claude Code/MYHaze/pipeline" run python -c "import numpy, lightgbm; print(numpy.__version__, lightgbm.__version__)"
```

Expected: two version numbers (numpy 2.x, lightgbm 4.x). The `brew` step is macOS-only; GitHub's Ubuntu runners need nothing extra.

- [ ] **Step 2: Write the failing tests**

`pipeline/tests/test_features.py`:

```python
from datetime import date, datetime, timedelta, timezone

import pytest

from myhaze.features import FEATURES, build_live_rows, build_rows, cell_arrays, upwind_by_region
from myhaze.rows import FireCell, HourlyWeather, Station
from myhaze.weather import RAIN_POINTS, WeatherDay

KLANG = Station("CA21B", "Klang", "Selangor", 3.04, 101.45)
KUCHING = Station("CA44Q", "Kuching", "Sarawak", 1.55, 110.35)
ISSUE = date(2026, 10, 10)
SW_WIND = WeatherDay(2.0, 3, 8.0, 15.0, 225.0, 80.0)  # wind blowing from the south-west


def inputs():
    daily_pm = {(s.station_id, ISSUE + timedelta(days=k)): 50.0 + k for s in (KLANG, KUCHING) for k in range(-4, 4)}
    cells = {ISSUE + timedelta(days=k): [FireCell(ISSUE + timedelta(days=k), 1.5, 101.25, 100.0 + k, 3)]
             for k in range(-5, 3)}
    weather = {(p.station_id, ISSUE + timedelta(days=lead), lead): SW_WIND
               for p in (KLANG, KUCHING, *RAIN_POINTS) for lead in (1, 2)}
    return daily_pm, cells, weather


def test_rows_have_every_feature_and_the_target():
    daily_pm, cells, weather = inputs()
    rows = build_rows([KLANG, KUCHING], daily_pm, cells, weather, [ISSUE])
    assert len(rows) == 4 and all(set(r.x) == set(FEATURES) for r in rows)
    klang_1 = next(r for r in rows if r.station_id == "CA21B" and r.lead == 1)
    assert (klang_1.target_day, klang_1.y, klang_1.x["pm_d0"], klang_1.x["pm_d2"]) == (ISSUE + timedelta(days=1), 51.0, 50.0, 48.0)
    assert klang_1.x["upwind_fire"] > 0  # the fire at 1.6N 101.4E is south of Klang, within 90 degrees of a south-west wind


def test_features_do_not_change_when_future_data_changes():
    daily_pm, cells, weather = inputs()
    base = build_rows([KLANG, KUCHING], daily_pm, cells, weather, [ISSUE])
    future_pm = {k: (v * 3 if k[1] > ISSUE else v) for k, v in daily_pm.items()}
    future_cells = {d: ([FireCell(c.day, c.lat_bin, c.lon_bin, c.frp_sum * 10, c.detections) for c in cs] if d >= ISSUE else cs)
                    for d, cs in cells.items()}
    again = build_rows([KLANG, KUCHING], future_pm, future_cells, weather, [ISSUE])
    assert [r.x for r in base] == [r.x for r in again]
    assert [r.y for r in base] != [r.y for r in again]


def test_upwind_counts_only_fires_the_wind_blows_from():
    arrays = cell_arrays([FireCell(ISSUE, 1.5, 101.25, 100.0, 1)])  # south of Klang, in Sumatra
    assert sum(upwind_by_region(KLANG, arrays, 225.0).values()) > 0
    assert sum(upwind_by_region(KLANG, arrays, 45.0).values()) == 0
    assert upwind_by_region(KLANG, arrays, 225.0)["sumatra"] > 0
    assert sum(upwind_by_region(KLANG, None, 225.0).values()) == 0


def test_live_rows_use_the_current_reading_and_the_live_forecast():
    daily_pm, cells, _ = inputs()
    now = datetime(2026, 10, 10, 2, tzinfo=timezone.utc)  # 10:00 MYT on the issue day
    start = datetime(2026, 10, 9, 16, tzinfo=timezone.utc)
    times = [start + timedelta(hours=h) for h in range(96)]
    hw = {p.station_id: HourlyWeather(p.station_id, times, [0.1] * 96, [400.0] * 96, [5.0] * 96, [12.0] * 96,
                                      [225.0] * 96, [75.0] * 96) for p in (KLANG, *RAIN_POINTS)}
    past_pm = {k: v for k, v in daily_pm.items() if k[1] <= ISSUE}  # live: nothing after today exists yet
    rows = build_live_rows([KLANG], now, {"CA21B": 88.0}, past_pm, cells, hw)
    assert [(r.lead, r.x["pm_d0"], r.y) for r in rows] == [(1, 88.0, None), (2, 88.0, None)]
    assert rows[0].x["wind_from_sin"] == pytest.approx(-0.7071, abs=1e-3)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest tests/test_features.py -q 2>&1 | tail -3`
Expected: FAIL. A collection error for `myhaze.features`.

- [ ] **Step 4: Write the implementation**

`pipeline/myhaze/features.py`:

```python
"""One feature builder for training and live forecasting, so the backtest cannot use hindsight.

Issue day D (a Malaysia date) predicts the daily-mean PM2.5 of target day D + lead from:
PM2.5 up to and including D; fire cells of the last complete UTC day before the issue (D - 1)
and three days before the issue (D - 3, for the trend); and weather *forecasts* for the target day.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np

from .config import MYT
from .geo import region_of
from .rows import FireCell, HourlyWeather, Station
from .sources.firms import GRID_DEG
from .weather import RAIN_POINTS, WeatherDay, daily_weather

REGION_GROUP = {"Perlis": 0, "Kedah": 0, "Pulau Pinang": 0, "Perak": 0, "Selangor": 0, "WP Kuala Lumpur": 0,
                "WP Putrajaya": 0, "Negeri Sembilan": 0, "Melaka": 0, "Kelantan": 1, "Terengganu": 1, "Pahang": 1,
                "Johor": 2, "Sarawak": 3, "Sabah": 4, "WP Labuan": 4}
FIRE_REGIONS = ("sumatra", "kalimantan", "peninsular", "my_borneo")
FEATURES = ("pm_d0", "pm_d1", "pm_d2", "pm_trend", "region_pm_d0", "upwind_fire", "fire_sumatra", "fire_kalimantan",
            "fire_peninsular", "fire_my_borneo", "fire_trend", "rain_mm", "wet_hours", "rain_fire_regions",
            "wind10_kmh", "wind120_kmh", "wind_from_sin", "wind_from_cos", "rh_mean", "lat", "lon", "region_group")
MONOTONE = {"upwind_fire": 1, "rain_mm": -1, "rain_fire_regions": -1}
UPWIND_EFOLD_KM = 500.0
EARTH_KM = 6371.0


@dataclass
class FeatureRow:
    station_id: str
    issue_day: date
    lead: int
    target_day: date
    x: dict[str, float | None]
    y: float | None
    upwind_by_region: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class CellArrays:
    lat: np.ndarray  # radians, cell centres
    lon: np.ndarray
    frp: np.ndarray
    region: np.ndarray


def cell_arrays(cells: list[FireCell]) -> CellArrays | None:
    if not cells:
        return None
    lat = np.array([c.lat_bin + GRID_DEG / 2 for c in cells])
    lon = np.array([c.lon_bin + GRID_DEG / 2 for c in cells])
    return CellArrays(np.radians(lat), np.radians(lon), np.array([c.frp_sum for c in cells], dtype=float),
                      np.array([region_of(la, lo) for la, lo in zip(lat, lon)]))


def region_totals(arrays: CellArrays | None) -> dict[str, float]:
    if arrays is None:
        return dict.fromkeys(FIRE_REGIONS, 0.0)
    return {r: float(arrays.frp[arrays.region == r].sum()) for r in FIRE_REGIONS}


def upwind_by_region(station: Station, arrays: CellArrays | None, wind_from_deg: float | None) -> dict[str, float]:
    """Fire power weighted by distance (e-folding 500 km) and by how squarely it lies upwind."""
    regions = dict.fromkeys(FIRE_REGIONS + ("other",), 0.0)
    if arrays is None or wind_from_deg is None:
        return regions
    lat1, lon1 = math.radians(station.lat), math.radians(station.lon)
    dl = arrays.lon - lon1
    a = np.sin((arrays.lat - lat1) / 2) ** 2 + math.cos(lat1) * np.cos(arrays.lat) * np.sin(dl / 2) ** 2
    km = 2 * EARTH_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    bearing = np.degrees(np.arctan2(np.sin(dl) * np.cos(arrays.lat),
                                    math.cos(lat1) * np.sin(arrays.lat) - math.sin(lat1) * np.cos(arrays.lat) * np.cos(dl)))
    align = np.clip(np.cos(np.radians(bearing - wind_from_deg)), 0.0, None)
    weight = arrays.frp * np.exp(-km / UPWIND_EFOLD_KM) * align
    return {r: float(weight[arrays.region == r].sum()) for r in regions}


def _region_means(stations: list[Station], daily_pm: dict, day: date) -> dict[int, float]:
    groups: dict[int, list[float]] = defaultdict(list)
    for s in stations:
        value = daily_pm.get((s.station_id, day))
        if value is not None:
            groups[REGION_GROUP.get(s.state, 0)].append(value)
    return {g: sum(v) / len(v) for g, v in groups.items()}


def _log_ratio(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else math.log1p(a) - math.log1p(b)


def build_rows(stations: list[Station], daily_pm: dict[tuple[str, date], float],
               cells_by_day: dict[date, list[FireCell]], weather: dict[tuple[str, date, int], WeatherDay],
               issue_days: list[date], leads: tuple[int, ...] = (1, 2)) -> list[FeatureRow]:
    arrays_cache: dict[date, CellArrays | None] = {}

    def arrays_for(day: date) -> CellArrays | None:
        if day not in arrays_cache:
            arrays_cache[day] = cell_arrays(cells_by_day.get(day, []))
        return arrays_cache[day]

    rows = []
    for issue in issue_days:
        fires = arrays_for(issue - timedelta(days=1))
        totals, totals_before = region_totals(fires), region_totals(arrays_for(issue - timedelta(days=3)))
        region_pm = _region_means(stations, daily_pm, issue)
        for lead in leads:
            target = issue + timedelta(days=lead)
            rain = [w.precip_mm for p in RAIN_POINTS
                    if (w := weather.get((p.station_id, target, lead))) is not None and w.precip_mm is not None]
            rain_fire = sum(rain) / len(rain) if rain else None
            for s in stations:
                pm0, pm1, pm2 = (daily_pm.get((s.station_id, issue - timedelta(days=k))) for k in range(3))
                wd = weather.get((s.station_id, target, lead))
                wind_from = wd.wind120_from_deg if wd else None
                upwind = upwind_by_region(s, fires, wind_from)
                x = {
                    "pm_d0": pm0, "pm_d1": pm1, "pm_d2": pm2, "pm_trend": _log_ratio(pm0, pm2),
                    "region_pm_d0": region_pm.get(REGION_GROUP.get(s.state, 0)),
                    "upwind_fire": math.log1p(sum(upwind.values())) if wind_from is not None else None,
                    **{f"fire_{r}": math.log1p(totals[r]) for r in FIRE_REGIONS},
                    "fire_trend": _log_ratio(sum(totals.values()), sum(totals_before.values())),
                    "rain_mm": wd.precip_mm if wd else None,
                    "wet_hours": float(wd.wet_hours) if wd and wd.wet_hours is not None else None,
                    "rain_fire_regions": rain_fire,
                    "wind10_kmh": wd.wind10_kmh if wd else None,
                    "wind120_kmh": wd.wind120_kmh if wd else None,
                    "wind_from_sin": math.sin(math.radians(wind_from)) if wind_from is not None else None,
                    "wind_from_cos": math.cos(math.radians(wind_from)) if wind_from is not None else None,
                    "rh_mean": wd.rh_mean if wd else None,
                    "lat": s.lat, "lon": s.lon, "region_group": float(REGION_GROUP.get(s.state, 0)),
                }
                rows.append(FeatureRow(s.station_id, issue, lead, target, x, daily_pm.get((s.station_id, target)),
                                       upwind))
    return rows


def live_weather_days(latest: dict[str, HourlyWeather], issue: date,
                      leads: tuple[int, ...] = (1, 2)) -> dict[tuple[str, date, int], WeatherDay]:
    days = {}
    for station_id, hw in latest.items():
        summary = daily_weather(hw)
        for lead in leads:
            target = issue + timedelta(days=lead)
            if target in summary:
                days[(station_id, target, lead)] = summary[target]
    return days


def build_live_rows(stations: list[Station], now: datetime, pm_now: dict[str, float],
                    daily_pm: dict[tuple[str, date], float], cells_by_day: dict[date, list[FireCell]],
                    weather_latest: dict[str, HourlyWeather], leads: tuple[int, ...] = (1, 2)) -> list[FeatureRow]:
    issue = now.astimezone(MYT).date()
    pm = {key: value for key, value in daily_pm.items() if key[1] < issue}
    pm.update({(station_id, issue): value for station_id, value in pm_now.items()})
    return build_rows(stations, pm, cells_by_day, live_weather_days(weather_latest, issue, leads), [issue], leads)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv --directory pipeline run pytest -q 2>&1 | tail -2`
Expected: all unit tests pass (4 new in `test_features.py`).

- [ ] **Step 6: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add -A pipeline
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): shared feature builder with upwind-fire index and no hindsight

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Metrics and baselines

**Files:**
- Create: `pipeline/myhaze/metrics.py`, `pipeline/myhaze/baselines.py`, `pipeline/tests/test_metrics.py`, `pipeline/tests/test_baselines.py`

**Interfaces:**
- Consumes:
  - `convert.band`, `convert.ugm3_to_api`
  - `features.FeatureRow`
- Produces:
  - `metrics.evaluate(records: list[dict]) -> dict`, where a record is `{"obs", "p50", optional "p10", "p90"}` in µg/m³. Returned keys: `n`, `band_accuracy`, `unhealthy_days`, `pod_unhealthy`, `far_unhealthy`, `mae_ugm3`, `coverage_80`.
  - `metrics.meets_target(scores) -> bool` (band ≥0.90 and POD ≥0.90; a missing POD counts as not met)
  - `baselines.persistence(row) -> float | None`
  - `baselines.cams_corrected(station_id, issue_day, target_day, cams_daily, daily_pm, window=7, min_days=3) -> float | None`

- [ ] **Step 1: Write the failing tests**

`pipeline/tests/test_metrics.py`:

```python
import pytest

from myhaze.convert import api_to_ugm3
from myhaze.metrics import evaluate, meets_target


def rec(obs_api, pred_api, low_api=None, high_api=None):
    r = {"obs": api_to_ugm3(obs_api), "p50": api_to_ugm3(pred_api)}
    if low_api is not None:
        r.update(p10=api_to_ugm3(low_api), p90=api_to_ugm3(high_api))
    return r


def test_evaluate_scores_bands_detection_and_coverage():
    scores = evaluate([rec(150, 160, 120, 190), rec(150, 90, 70, 110), rec(60, 70, 50, 90), rec(40, 120, 100, 140)])
    assert scores["n"] == 4
    assert scores["band_accuracy"] == pytest.approx(0.5)
    assert (scores["unhealthy_days"], scores["pod_unhealthy"]) == (2, 0.5)
    assert scores["far_unhealthy"] == pytest.approx(0.5)
    assert scores["coverage_80"] == pytest.approx(0.5)


def test_evaluate_without_unhealthy_days_has_no_pod():
    scores = evaluate([rec(40, 45), rec(60, 55)])
    assert scores["pod_unhealthy"] is None and scores["coverage_80"] is None and scores["band_accuracy"] == 1.0


def test_meets_target_needs_both_bars():
    assert meets_target({"band_accuracy": 0.92, "pod_unhealthy": 0.91})
    assert not meets_target({"band_accuracy": 0.95, "pod_unhealthy": 0.80})
    assert not meets_target({"band_accuracy": 0.95, "pod_unhealthy": None})
```

`pipeline/tests/test_baselines.py`:

```python
from datetime import date, timedelta

from myhaze.baselines import cams_corrected, persistence
from myhaze.features import FeatureRow

D = date(2026, 10, 10)


def test_persistence_is_the_issue_day_mean():
    row = FeatureRow("S", D, 1, D + timedelta(days=1), {"pm_d0": 61.5}, None)
    assert persistence(row) == 61.5


def test_cams_corrected_scales_by_recent_observed_over_modelled():
    daily_pm = {("S", D - timedelta(days=k)): 60.0 for k in range(7)}
    cams = {("S", D - timedelta(days=k)): 30.0 for k in range(7)}
    cams[("S", D + timedelta(days=1))] = 40.0
    assert cams_corrected("S", D, D + timedelta(days=1), cams, daily_pm) == 80.0
    assert cams_corrected("S", D, D + timedelta(days=2), cams, daily_pm) is None
    assert cams_corrected("S", D, D + timedelta(days=1), cams, {("S", D): 60.0}) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest tests/test_metrics.py tests/test_baselines.py -q 2>&1 | tail -3`
Expected: FAIL. Collection errors for `myhaze.metrics` and `myhaze.baselines`.

- [ ] **Step 3: Write the implementation**

`pipeline/myhaze/metrics.py`:

```python
"""Forecast scores on the official API scale: the band people see, and whether bad days were caught."""
from __future__ import annotations

from .convert import band, ugm3_to_api

OK_BANDS = ("good", "moderate")


def evaluate(records: list[dict]) -> dict:
    rows = [r for r in records if r.get("obs") is not None and r.get("p50") is not None]
    if not rows:
        return {"n": 0, "band_accuracy": None, "unhealthy_days": 0, "pod_unhealthy": None, "far_unhealthy": None,
                "mae_ugm3": None, "coverage_80": None}
    obs_bands = [band(ugm3_to_api(r["obs"])) for r in rows]
    pred_bands = [band(ugm3_to_api(r["p50"])) for r in rows]
    obs_bad = [b not in OK_BANDS for b in obs_bands]
    pred_bad = [b not in OK_BANDS for b in pred_bands]
    caught = sum(p and o for p, o in zip(pred_bad, obs_bad))
    false_alarms = sum(p and not o for p, o in zip(pred_bad, obs_bad))
    bad_days = sum(obs_bad)
    ranged = [r for r in rows if r.get("p10") is not None and r.get("p90") is not None]
    return {
        "n": len(rows),
        "band_accuracy": round(sum(p == o for p, o in zip(pred_bands, obs_bands)) / len(rows), 4),
        "unhealthy_days": bad_days,
        "pod_unhealthy": round(caught / bad_days, 4) if bad_days else None,
        "far_unhealthy": round(false_alarms / (caught + false_alarms), 4) if caught + false_alarms else None,
        "mae_ugm3": round(sum(abs(r["p50"] - r["obs"]) for r in rows) / len(rows), 2),
        "coverage_80": round(sum(r["p10"] <= r["obs"] <= r["p90"] for r in ranged) / len(ranged), 4) if ranged else None,
    }


def meets_target(scores: dict) -> bool:
    return (scores.get("band_accuracy") or 0) >= 0.90 and (scores.get("pod_unhealthy") or 0) >= 0.90
```

`pipeline/myhaze/baselines.py`:

```python
"""The simple forecasts the trained model must beat."""
from __future__ import annotations

from datetime import date, timedelta

from .features import FeatureRow


def persistence(row: FeatureRow) -> float | None:
    """Tomorrow looks like today."""
    return row.x.get("pm_d0")


def cams_corrected(station_id: str, issue_day: date, target_day: date, cams_daily: dict[tuple[str, date], float],
                   daily_pm: dict[tuple[str, date], float], window: int = 7, min_days: int = 3) -> float | None:
    """CAMS's daily mean for the target day, scaled by how far CAMS was off at this station over the last week."""
    target = cams_daily.get((station_id, target_day))
    if target is None:
        return None
    observed = modelled = 0.0
    days = 0
    for k in range(window):
        day = issue_day - timedelta(days=k)
        obs, cams = daily_pm.get((station_id, day)), cams_daily.get((station_id, day))
        if obs is not None and cams is not None and cams > 0:
            observed += obs
            modelled += cams
            days += 1
    if days < min_days or modelled <= 0:
        return None
    return target * observed / modelled
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory pipeline run pytest -q 2>&1 | tail -2`
Expected: all unit tests pass (5 new).

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add -A pipeline
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): forecast metrics and the persistence and corrected-CAMS baselines

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 7: Quantile model, backtest, model storage, weekly training

**Files:**
- Create: `pipeline/myhaze/model/__init__.py`, `pipeline/myhaze/model/quantile.py`, `pipeline/myhaze/model/backtest.py`, `pipeline/myhaze/jobs/train.py`, `supabase/migrations/0005_models.sql`, `.github/workflows/train.yml`, `pipeline/tests/test_quantile.py`, `pipeline/tests/test_backtest.py`
- Modify: `pipeline/myhaze/store.py`, `pipeline/tests/test_store_integration.py`

**Interfaces:**
- Consumes:
  - `features.FEATURES`, `MONOTONE`, `FeatureRow`, `build_rows`
  - `metrics.evaluate`, `meets_target`
  - `baselines.persistence`, `cams_corrected`
  - `load_daily.refresh_archive_daily`
  - `backfill.BACKFILLS`, `backfill.HISTORY_START`
- Produces:
  - `quantile.QUANTILES = (0.1, 0.5, 0.9)`
  - `quantile.matrix(rows) -> np.ndarray`
  - `quantile.choose_rounds(train, tune) -> int`
  - `quantile.fit(rows, rounds=300) -> dict[float, Booster]`
  - `quantile.predict(boosters, rows) -> list[tuple[float, float, float]]` (µg/m³, sorted low/mid/high)
  - `quantile.contributions(booster, rows) -> list[dict[str, float]]`
  - `quantile.to_text(boosters) -> dict[float, str]`, `quantile.from_text(texts) -> dict[float, Booster]`
  - `backtest.TRAIN_END = date(2026, 9, 15)`, `backtest.TUNE_END = date(2026, 9, 30)`
  - `backtest.run_backtest(rows, cams_daily, daily_pm, train_end=TRAIN_END, tune_end=TUNE_END) -> dict`. Its `report["leads"]["1"|"2"]` holds the keys `rounds`, `n_train`, `test_from`, `test_to`, `model`, `persistence`, `cams`, `method`, `meets_target`.
  - `backtest.choose_method(scores) -> "model" | "persistence" | "cams"`
  - `backtest.render_markdown(report) -> str`
  - `Store.save_model_version(version, methods: dict[int, str], report: dict, boosters: dict[int, dict[float, str]])`
  - `Store.load_model(version) -> tuple[dict[int, str], dict, dict[int, dict[float, str]]] | None`
  - `Store.latest_model_version() -> str | None`
  - `Store.prune_models(keep=4)`
  - CLI: `python -m myhaze.jobs.train` (exit 1 with "cannot train yet" when there isn't enough history)

- [ ] **Step 1: Write the failing tests**

`pipeline/tests/test_quantile.py`:

```python
import random
from dataclasses import replace
from datetime import date, timedelta

import pytest

from myhaze.features import FEATURES, FeatureRow
from myhaze.model.quantile import contributions, fit, from_text, predict, to_text


def rows_for(n=240, seed=1):
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        fire = rng.random()
        x = dict.fromkeys(FEATURES, None)
        x.update(pm_d0=40 + 60 * rng.random(), upwind_fire=fire * 5, lat=3.0, lon=101.5, region_group=0.0)
        day = date(2026, 7, 1) + timedelta(days=i % 90)
        rows.append(FeatureRow("S", day, 1, day + timedelta(days=1), x, 30 + 100 * fire))
    return rows


def test_fit_predict_orders_quantiles_and_survives_serialisation():
    rows = rows_for()
    boosters = fit(rows, rounds=60)
    preds = predict(boosters, rows[:5])
    assert all(low <= mid <= high for low, mid, high in preds)
    again = predict(from_text(to_text(boosters)), rows[:5])
    assert [v for p in again for v in p] == pytest.approx([v for p in preds for v in p])


def test_more_upwind_fire_never_lowers_the_forecast():
    boosters = fit(rows_for(), rounds=60)
    base = rows_for(1)[0]
    calm = replace(base, x=dict(base.x, upwind_fire=0.5))
    smoky = replace(base, x=dict(base.x, upwind_fire=4.5))
    (_, calm_mid, _), (_, smoky_mid, _) = predict(boosters, [calm, smoky])
    assert smoky_mid >= calm_mid


def test_contributions_cover_every_feature():
    boosters = fit(rows_for(), rounds=30)
    contrib = contributions(boosters[0.5], rows_for(2))
    assert len(contrib) == 2 and set(contrib[0]) == set(FEATURES)
```

`pipeline/tests/test_backtest.py`:

```python
import random
from datetime import date, timedelta

import pytest

from myhaze.features import FEATURES, FeatureRow
from myhaze.model.backtest import choose_method, render_markdown, run_backtest


def synthetic():
    rng = random.Random(3)
    start = date(2026, 7, 1)
    fire = [rng.random() for _ in range(130)]

    def truth(t):
        return 5 + 120 * fire[t]

    rows, cams, daily = [], {}, {}
    for s in range(4):
        sid = f"S{s}"
        for t in range(120):
            day = start + timedelta(days=t)
            daily[(sid, day)] = truth(t)
            cams[(sid, day)] = truth(t) * rng.uniform(0.5, 1.6)
        for t in range(3, 110):
            issue = start + timedelta(days=t)
            for lead in (1, 2):
                x = dict.fromkeys(FEATURES, None)
                x.update(pm_d0=truth(t), upwind_fire=fire[t + lead] * 5, lat=1.0 + s, lon=101.0, region_group=0.0)
                rows.append(FeatureRow(sid, issue, lead, issue + timedelta(days=lead), x, truth(t + lead)))
    return rows, cams, daily


def test_backtest_prefers_a_model_that_beats_both_baselines():
    rows, cams, daily = synthetic()
    report = run_backtest(rows, cams, daily)
    lead1 = report["leads"]["1"]
    assert lead1["model"]["band_accuracy"] > lead1["persistence"]["band_accuracy"]
    assert lead1["model"]["band_accuracy"] > lead1["cams"]["band_accuracy"]
    assert lead1["method"] == "model"
    assert "| Lead |" in render_markdown(report)


def test_backtest_refuses_when_a_window_is_empty():
    rows, cams, daily = synthetic()
    with pytest.raises(ValueError):
        run_backtest([r for r in rows if r.target_day > date(2026, 9, 30)], cams, daily)


def test_choose_method_falls_back_to_the_better_baseline():
    model = {"band_accuracy": 0.70, "pod_unhealthy": 0.95}
    assert choose_method({"model": model, "persistence": {"band_accuracy": 0.80, "pod_unhealthy": 0.9},
                          "cams": {"band_accuracy": 0.60, "pod_unhealthy": 0.9}}) == "persistence"
    assert choose_method({"model": model, "persistence": {"band_accuracy": 0.50, "pod_unhealthy": 0.9},
                          "cams": {"band_accuracy": 0.65, "pod_unhealthy": 0.96}}) == "cams"
```

Append to `pipeline/tests/test_store_integration.py`:

```python
def test_model_versions_roundtrip(store):
    try:
        store.save_model_version("ZZ0001", {1: "model", 2: "persistence"}, {"note": "test"},
                                 {1: {0.1: "low-text", 0.5: "mid-text", 0.9: "high-text"}, 2: {}})
        methods, report, boosters = store.load_model("ZZ0001")
        assert methods == {1: "model", 2: "persistence"} and report == {"note": "test"}
        assert boosters == {1: {0.1: "low-text", 0.5: "mid-text", 0.9: "high-text"}}
        assert store.load_model("ZZ-missing") is None
    finally:
        store.conn.execute("delete from model_versions where version like 'ZZ%'")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest -q 2>&1 | tail -3`
Expected: FAIL. Collection errors for `myhaze.model.quantile` and `myhaze.model.backtest`.

- [ ] **Step 3: Write the implementation**

`pipeline/myhaze/model/__init__.py`:

```python
"""Forecast model: daily quantile model, hourly shaping, closure indicator and explanations."""
```

`pipeline/myhaze/model/quantile.py`:

```python
"""LightGBM quantile models of daily-mean PM2.5, trained on log1p(µg/m³)."""
from __future__ import annotations

import lightgbm as lgb
import numpy as np

from ..features import FEATURES, MONOTONE, FeatureRow

QUANTILES = (0.1, 0.5, 0.9)
DEFAULT_ROUNDS = 300
PARAMS = {
    "objective": "quantile", "learning_rate": 0.05, "num_leaves": 15, "min_data_in_leaf": 30,
    "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
    "verbose": -1, "seed": 7, "deterministic": True, "num_threads": 1,
    "monotone_constraints": [MONOTONE.get(f, 0) for f in FEATURES],
}


def matrix(rows: list[FeatureRow]) -> np.ndarray:
    return np.array([[np.nan if r.x.get(f) is None else float(r.x[f]) for f in FEATURES] for r in rows],
                    dtype=float).reshape(len(rows), len(FEATURES))


def _dataset(rows: list[FeatureRow], reference: lgb.Dataset | None = None) -> lgb.Dataset:
    labelled = [r for r in rows if r.y is not None]
    if not labelled:
        raise ValueError("no labelled rows")
    return lgb.Dataset(matrix(labelled), label=np.log1p([r.y for r in labelled]), feature_name=list(FEATURES),
                       categorical_feature=["region_group"], reference=reference, free_raw_data=False)


def choose_rounds(train_rows: list[FeatureRow], tune_rows: list[FeatureRow], max_rounds: int = 600) -> int:
    train = _dataset(train_rows)
    tune = _dataset(tune_rows, reference=train)
    booster = lgb.train(dict(PARAMS, alpha=0.5), train, num_boost_round=max_rounds, valid_sets=[tune],
                        callbacks=[lgb.early_stopping(30, verbose=False)])
    return max(booster.best_iteration or DEFAULT_ROUNDS, 20)


def fit(rows: list[FeatureRow], rounds: int = DEFAULT_ROUNDS) -> dict[float, lgb.Booster]:
    data = _dataset(rows)
    return {q: lgb.train(dict(PARAMS, alpha=q), data, num_boost_round=rounds) for q in QUANTILES}


def predict(boosters: dict[float, lgb.Booster], rows: list[FeatureRow]) -> list[tuple[float, float, float]]:
    if not rows:
        return []
    x = matrix(rows)
    columns = [np.expm1(boosters[q].predict(x)) for q in QUANTILES]
    return [tuple(sorted(max(float(v), 0.0) for v in triple)) for triple in zip(*columns)]


def contributions(booster: lgb.Booster, rows: list[FeatureRow]) -> list[dict[str, float]]:
    """Per-feature effect on log1p(PM2.5) for each row (LightGBM's built-in SHAP values, bias column dropped)."""
    if not rows:
        return []
    values = booster.predict(matrix(rows), pred_contrib=True)
    return [dict(zip(FEATURES, (float(v) for v in row[:-1]))) for row in values]


def to_text(boosters: dict[float, lgb.Booster]) -> dict[float, str]:
    return {q: b.model_to_string() for q, b in boosters.items()}


def from_text(texts: dict[float, str]) -> dict[float, lgb.Booster]:
    return {float(q): lgb.Booster(model_str=t) for q, t in texts.items()}
```

`pipeline/myhaze/model/backtest.py`:

```python
"""Backtest the model against persistence and corrected CAMS on held-out days, and choose what ships."""
from __future__ import annotations

from datetime import date

from ..baselines import cams_corrected, persistence
from ..features import FeatureRow
from ..metrics import evaluate, meets_target
from .quantile import choose_rounds, fit, predict

TRAIN_END = date(2026, 9, 15)
TUNE_END = date(2026, 9, 30)


def _scores(test: list[FeatureRow], preds, cams_daily, daily_pm) -> dict:
    model, persist, cams = [], [], []
    for row, (low, mid, high) in zip(test, preds):
        p = persistence(row)
        c = cams_corrected(row.station_id, row.issue_day, row.target_day, cams_daily, daily_pm)
        if p is None or c is None:
            continue  # all three methods are scored on exactly the same days
        model.append({"obs": row.y, "p10": low, "p50": mid, "p90": high})
        persist.append({"obs": row.y, "p50": p})
        cams.append({"obs": row.y, "p50": c})
    return {"model": evaluate(model), "persistence": evaluate(persist), "cams": evaluate(cams)}


def _beats(a: dict, b: dict) -> bool:
    return ((a.get("band_accuracy") or 0) >= (b.get("band_accuracy") or 0)
            and (a.get("pod_unhealthy") or 0) >= (b.get("pod_unhealthy") or 0))


def choose_method(scores: dict) -> str:
    if _beats(scores["model"], scores["persistence"]) and _beats(scores["model"], scores["cams"]):
        return "model"
    p, c = scores["persistence"], scores["cams"]
    return "persistence" if (p.get("band_accuracy") or 0) >= (c.get("band_accuracy") or 0) else "cams"


def run_backtest(rows: list[FeatureRow], cams_daily: dict, daily_pm: dict, train_end: date = TRAIN_END,
                 tune_end: date = TUNE_END) -> dict:
    report: dict = {"train_end": train_end.isoformat(), "tune_end": tune_end.isoformat(), "leads": {}}
    for lead in (1, 2):
        labelled = [r for r in rows if r.lead == lead and r.y is not None]
        train = [r for r in labelled if r.target_day <= train_end]
        tune = [r for r in labelled if train_end < r.target_day <= tune_end]
        test = [r for r in labelled if r.target_day > tune_end]
        if not train or not tune or not test:
            raise ValueError(f"lead {lead}: need labelled rows in train/tune/test windows "
                             f"(have {len(train)}/{len(tune)}/{len(test)})")
        rounds = choose_rounds(train, tune)
        scores = _scores(test, predict(fit(train + tune, rounds), test), cams_daily, daily_pm)
        report["leads"][str(lead)] = {
            "rounds": rounds, "n_train": len(train) + len(tune),
            "test_from": min(r.target_day for r in test).isoformat(),
            "test_to": max(r.target_day for r in test).isoformat(),
            **scores, "method": choose_method(scores), "meets_target": meets_target(scores["model"]),
        }
    return report


def _pct(value) -> str:
    return "–" if value is None else f"{value * 100:.1f}%"


def render_markdown(report: dict) -> str:
    lines = ["# MYHaze backtest", "",
             f"Trained on days up to {report['tune_end']}; tested on later days. Bands are the official API "
             "bands of each day's average PM2.5. Target for tomorrow: ≥90% correct band and ≥90% of "
             "unhealthy-or-worse days caught.", "",
             "| Lead | Method | Days | Correct band | Unhealthy+ caught | False alarms | Avg miss (µg/m³) | In 80% range |",
             "|---|---|---|---|---|---|---|---|"]
    for lead, entry in report["leads"].items():
        label = "Tomorrow" if lead == "1" else "Day after"
        for method in ("model", "persistence", "cams"):
            s = entry[method]
            chosen = " (shipped)" if entry["method"] == method else ""
            lines.append(f"| {label} | {method}{chosen} | {s['n']} | {_pct(s['band_accuracy'])} | "
                         f"{_pct(s['pod_unhealthy'])} | {_pct(s['far_unhealthy'])} | {s['mae_ugm3']} | "
                         f"{_pct(s['coverage_80'])} |")
    lead1 = report["leads"].get("1", {})
    lines += ["", f"Tomorrow's target met: **{'yes' if lead1.get('meets_target') else 'no'}**."]
    return "\n".join(lines) + "\n"
```

`supabase/migrations/0005_models.sql`:

```sql
-- Trained model versions (report and the method shipped per lead) and their LightGBM boosters as text.
create table model_versions (
  version text primary key,
  created_at timestamptz not null default now(),
  methods jsonb not null,
  report jsonb not null
);

create table model_boosters (
  version text not null references model_versions (version) on delete cascade,
  lead_days smallint not null,
  quantile double precision not null,
  booster text not null,
  primary key (version, lead_days, quantile)
);

alter table model_versions enable row level security;
alter table model_boosters enable row level security;
```

Append to `Store`:

```python
    def save_model_version(self, version: str, methods: dict[int, str], report: dict,
                           boosters: dict[int, dict[float, str]]) -> None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute("insert into model_versions (version, methods, report) values (%s, %s, %s)",
                        (version, Jsonb({str(k): v for k, v in methods.items()}), Jsonb(report)))
            rows = [(version, lead, q, text) for lead, by_q in boosters.items() for q, text in by_q.items()]
            if rows:
                cur.executemany("insert into model_boosters (version, lead_days, quantile, booster) "
                                "values (%s, %s, %s, %s)", rows)

    def load_model(self, version: str) -> tuple[dict[int, str], dict, dict[int, dict[float, str]]] | None:
        head = self.conn.execute("select methods, report from model_versions where version = %s",
                                 (version,)).fetchone()
        if head is None:
            return None
        boosters: dict[int, dict[float, str]] = {}
        for lead, q, text in self.conn.execute(
                "select lead_days, quantile, booster from model_boosters where version = %s", (version,)).fetchall():
            boosters.setdefault(int(lead), {})[float(q)] = text
        return {int(k): v for k, v in head[0].items()}, head[1], boosters

    def latest_model_version(self) -> str | None:
        row = self.conn.execute("select version from model_versions order by created_at desc limit 1").fetchone()
        return row[0] if row else None

    def prune_models(self, keep: int = 4) -> None:
        self.conn.execute("delete from model_versions where version not in "
                          "(select version from model_versions order by created_at desc limit %s)", (keep,))
```

`pipeline/myhaze/jobs/train.py`:

```python
"""Weekly: refresh history, backtest, train the final models, store them and write the public report."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from ..config import MYT, REPO_ROOT, load_settings
from ..features import build_rows
from ..http import make_client
from ..model.backtest import render_markdown, run_backtest
from ..model.quantile import fit, to_text
from ..store import Store
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
    cells_by_day = defaultdict(list)
    for cell in store.fire_cells(start - timedelta(days=4), today):
        cells_by_day[cell.day].append(cell)
    daily_pm = store.daily_pm25(start - timedelta(days=3), today)
    weather = store.weather_daily(start, today + timedelta(days=2))
    cams_daily = store.cams_daily(start - timedelta(days=7), today)
    issue_days = [start + timedelta(days=i) for i in range((today - start).days)]
    return build_rows(store.stations(), daily_pm, cells_by_day, weather, issue_days), cams_daily, daily_pm


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    if not settings.db_url:
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 2
    today = datetime.now(MYT).date()
    store = Store.connect(settings.db_url)
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
```

`.github/workflows/train.yml`:

```yaml
name: train

on:
  schedule:
    - cron: "0 19 * * 6"  # Sunday 03:00 Malaysia time
  workflow_dispatch:

concurrency:
  group: train
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  train:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
        with:
          enable-cache: true
          cache-dependency-glob: pipeline/uv.lock
      - name: Install
        run: uv --directory pipeline sync --frozen
      - name: Train and backtest
        run: uv --directory pipeline run python -m myhaze.jobs.train
        env:
          SUPABASE_DB_URL: ${{ secrets.SUPABASE_DB_URL }}
      - name: Commit the backtest report
        run: |
          git config user.name "myhaze-bot"
          git config user.email "myhaze-bot@users.noreply.github.com"
          git add docs/backtest
          git diff --cached --quiet || git commit -m "chore: weekly backtest report"
          git push
```

The weekly report commit also keeps the repository active, so GitHub doesn't disable the scheduled workflows after 60 quiet days.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory pipeline run python -m myhaze.migrate && uv --directory pipeline run pytest -m "integration or not integration" -q 2>&1 | tail -2`
Expected: `applied: 0005_models.sql`, then all pass (6 new unit tests + 1 integration test).

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add -A pipeline supabase .github
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): quantile model, backtest against baselines, weekly training job

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Train for real (after the aqicn CSVs are loaded in Task 3 Step 5)**

```bash
uv --directory pipeline run python -m myhaze.jobs.load_daily
uv --directory pipeline run python -m myhaze.jobs.train
cat "/Users/ryanchuah/Claude Code/MYHaze/docs/backtest/latest.md"
```

Expected: two `lead N: ships …` lines, a version, and the markdown table. **Read the table and report it to the owner verbatim**: whether tomorrow's target (≥90% band, ≥90% unhealthy caught) was met, and which method ships. Without CSV exports it prints `cannot train yet: …` and exits 1. That's expected; the forecast job then uses persistence.

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add docs/backtest
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "docs: first backtest report

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Hourly path, official API forecast, closure indicator, explanations

**Files:**
- Create: `pipeline/myhaze/model/hourly.py`, `pipeline/myhaze/model/closure.py`, `pipeline/myhaze/model/explain.py`, `pipeline/tests/test_hourly.py`, `pipeline/tests/test_closure.py`, `pipeline/tests/test_explain.py`

**Interfaces:**
- Consumes:
  - `convert.ugm3_to_api`
  - `rows.HourlyWeather`
  - `features.FeatureRow`, `features.FIRE_REGIONS`
  - `config.MYT`
- Produces:
  - `hourly.HORIZON_H = 48`
  - `hourly.HourlyPath(times, p10, p50, p90, trapped)`, with values in µg/m³ and `times` starting at the current UTC hour
  - `hourly.build_path(now_hour, levels: dict[date, tuple[float, float, float]], weather: HourlyWeather | None, anchor: float | None) -> HourlyPath`
  - `hourly.official_api_path(path, observed: dict[datetime, float], fallback: float | None) -> tuple[list, list, list]` (API low/mid/high per hour)
  - `closure.is_school_day(day, state) -> bool`
  - `closure.next_school_day(now, state) -> date`
  - `closure.p_above(p50, low, high, threshold) -> float`
  - `closure.closure_indicator(state, now, times, official, observed_daily_max: dict[date, float]) -> dict`, returning `{"school_day", "probability" | None, "rule"}`
  - `explain.compass(deg) -> str`
  - `explain.explain(contrib, row, *, rain_window=None, trapped_window=None, limit=3) -> list[str]`

- [ ] **Step 1: Write the failing tests**

`pipeline/tests/test_hourly.py`:

```python
from datetime import date, datetime, timedelta, timezone

import pytest

from myhaze.convert import ugm3_to_api
from myhaze.model.hourly import build_path, official_api_path
from myhaze.rows import HourlyWeather

NOW = datetime(2026, 10, 15, 2, tzinfo=timezone.utc)  # 10:00 MYT, Thursday
DAYS = (date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 17))
FLAT = {d: (50.0, 50.0, 50.0) for d in DAYS}


def weather(blh_for_local_hour=lambda h: 500.0, rain_at=()):
    start = datetime(2026, 10, 14, 16, tzinfo=timezone.utc)  # 00:00 MYT on the 15th
    times = [start + timedelta(hours=h) for h in range(96)]
    local_hour = [(t + timedelta(hours=8)).hour for t in times]
    return HourlyWeather("S", times, [5.0 if t in rain_at else 0.0 for t in times],
                         [blh_for_local_hour(h) for h in local_hour], [3.0] * 96, [10.0] * 96, [225.0] * 96,
                         [80.0] * 96)


def test_path_starts_at_the_live_reading_and_relaxes_to_the_model():
    levels = {DAYS[0]: (40.0, 50.0, 70.0), DAYS[1]: (60.0, 80.0, 110.0), DAYS[2]: (50.0, 70.0, 100.0)}
    path = build_path(NOW, levels, weather(), anchor=100.0)
    assert len(path.times) == 48 and path.times[0] == NOW
    assert path.p10[0] == path.p50[0] == path.p90[0] == pytest.approx(100.0)
    tomorrow_noon = path.times.index(datetime(2026, 10, 16, 4, tzinfo=timezone.utc))
    assert path.p50[tomorrow_noon] == pytest.approx(80.0, rel=0.02)
    assert path.p10[tomorrow_noon] < path.p50[tomorrow_noon] < path.p90[tomorrow_noon]


def test_shallow_mornings_raise_and_rain_lowers_the_path():
    shallow = weather(lambda h: 100.0 if 6 <= h <= 9 else 1000.0)
    path = build_path(NOW, FLAT, shallow, anchor=None)
    morning = path.times.index(datetime(2026, 10, 15, 23, tzinfo=timezone.utc))  # 07:00 MYT on the 16th
    midday = path.times.index(datetime(2026, 10, 16, 5, tzinfo=timezone.utc))    # 13:00 MYT
    assert path.p50[morning] > path.p50[midday] and path.trapped[morning] and not path.trapped[midday]

    rain_hour = datetime(2026, 10, 16, 5, tzinfo=timezone.utc)
    wet = build_path(NOW, FLAT, weather(lambda h: 100.0 if 6 <= h <= 9 else 1000.0, rain_at=(rain_hour,)), None)
    assert wet.p50[midday] == pytest.approx(path.p50[midday] * 0.85, rel=1e-3)


def test_official_api_is_a_24_hour_mean_of_observed_and_forecast():
    path = build_path(NOW, FLAT, None, anchor=None)
    observed = {NOW - timedelta(hours=k): 100.0 for k in range(1, 24)}
    low, mid, high = official_api_path(path, observed, fallback=None)
    assert mid[0] == pytest.approx(ugm3_to_api((23 * 100.0 + 50.0) / 24), abs=0.1)
    assert mid[23] == pytest.approx(ugm3_to_api(50.0), abs=0.1)
    assert len(low) == len(high) == 48
```

`pipeline/tests/test_closure.py`:

```python
from datetime import date, datetime, timedelta, timezone

import pytest

from myhaze.model.closure import closure_indicator, next_school_day, p_above


def test_next_school_day_respects_state_weeks():
    friday_evening = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)  # Fri 20:00 MYT
    assert next_school_day(friday_evening, "Selangor") == date(2026, 10, 19)  # Monday
    assert next_school_day(friday_evening, "Kedah") == date(2026, 10, 18)     # Sunday: Sun–Thu school week
    early_thursday = datetime(2026, 10, 14, 22, tzinfo=timezone.utc)          # Thu 06:00 MYT
    assert next_school_day(early_thursday, "Johor") == date(2026, 10, 15)


def test_p_above():
    assert p_above(180, 150, 216, 180) == pytest.approx(0.5, abs=0.01)
    assert p_above(100, 90, 110, 180) < 0.01
    assert p_above(200, None, None, 180) == 1.0


def test_closure_indicator_uses_the_three_day_rule_with_observed_days():
    now = datetime(2026, 10, 15, 2, tzinfo=timezone.utc)  # Thu 10:00 MYT, so the next school day is Friday
    times = [now + timedelta(hours=h) for h in range(48)]
    official = ([150.0] * 48, [160.0] * 48, [170.0] * 48)
    streak = closure_indicator("Selangor", now, times, official, {date(2026, 10, 14): 155, date(2026, 10, 15): 158})
    assert (streak["school_day"], streak["rule"]) == ("2026-10-16", "three_days_above_150")
    assert streak["probability"] > 0.9
    broken = closure_indicator("Selangor", now, times, official, {date(2026, 10, 14): 140, date(2026, 10, 15): 158})
    assert broken["rule"] == "api_above_180" and broken["probability"] < 0.05


def test_closure_indicator_beyond_the_horizon_has_no_probability():
    friday_evening = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    times = [friday_evening + timedelta(hours=h) for h in range(48)]  # ends Sunday 20:00 MYT
    result = closure_indicator("Selangor", friday_evening, times, ([1.0] * 48,) * 3, {})
    assert result == {"school_day": "2026-10-19", "probability": None, "rule": None}
```

`pipeline/tests/test_explain.py`:

```python
import math
from datetime import date, timedelta

from myhaze.features import FeatureRow
from myhaze.model.explain import compass, explain

D = date(2026, 10, 15)


def test_explain_ranks_families_and_names_the_fire_region():
    x = {"wind_from_sin": math.sin(math.radians(225)), "wind_from_cos": math.cos(math.radians(225))}
    row = FeatureRow("S", D, 1, D + timedelta(days=1), x, None,
                     {"sumatra": 50.0, "kalimantan": 5.0, "peninsular": 0.0, "my_borneo": 0.0, "other": 0.0})
    contrib = {"upwind_fire": 0.30, "fire_sumatra": 0.05, "rain_mm": -0.12, "pm_d0": 0.02, "wind_from_sin": 0.08}
    assert explain(contrib, row, rain_window="tomorrow afternoon", trapped_window="early tomorrow morning") == [
        "Fires upwind, mainly in Sumatra, are adding smoke.",
        "Rain expected tomorrow afternoon should help clear the air.",
        "Winds from the south-west are carrying smoke in.",
        "Smoke is likely to be trapped near the ground early tomorrow morning.",
    ]


def test_explain_without_contributions_keeps_only_weather_notes():
    row = FeatureRow("S", D, 1, D + timedelta(days=1), {}, None)
    assert explain({}, row, trapped_window="early tomorrow morning") == [
        "Smoke is likely to be trapped near the ground early tomorrow morning."]


def test_compass():
    assert [compass(d) for d in (0, 44, 90, 225, 350)] == ["north", "north-east", "east", "south-west", "north"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest tests/test_hourly.py tests/test_closure.py tests/test_explain.py -q 2>&1 | tail -3`
Expected: FAIL. Collection errors for the three new modules.

- [ ] **Step 3: Write the implementation**

`pipeline/myhaze/model/hourly.py`:

```python
"""Turn daily forecast levels into a 48-hour path of hourly PM2.5 (µg/m³).

The path starts at the live reading and relaxes to the model (e-folding 6 h). It is shaped by
forecast mixing height (smoke concentrates under a shallow early-morning layer) and lowered by rain.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from ..config import MYT
from ..convert import ugm3_to_api
from ..rows import HourlyWeather

HORIZON_H = 48
ANCHOR_EFOLD_H = 6.0
BLH_EXPONENT = 0.3
FACTOR_RANGE = (0.6, 1.8)
TRAPPED_FACTOR = 1.3
WASHOUT = 0.85
WASHOUT_MM = 1.0


@dataclass
class HourlyPath:
    times: list[datetime]
    p10: list[float]
    p50: list[float]
    p90: list[float]
    trapped: list[bool]


def _noon(day: date) -> datetime:
    return datetime.combine(day, time(12), MYT).astimezone(timezone.utc)


def _level(t: datetime, levels: dict[date, tuple[float, float, float]]) -> tuple[float, float, float]:
    """Log-linear between the noon points of consecutive days; flat beyond the first and last."""
    points = [(_noon(d), levels[d]) for d in sorted(levels)]
    if t <= points[0][0]:
        return points[0][1]
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        if t <= t1:
            w = (t - t0) / (t1 - t0)
            return tuple(math.exp((1 - w) * math.log(max(a, 0.1)) + w * math.log(max(b, 0.1))) for a, b in zip(v0, v1))
    return points[-1][1]


def diurnal_factors(weather: HourlyWeather | None) -> dict[datetime, float]:
    if weather is None:
        return {}
    by_day: dict[date, list[tuple[datetime, float]]] = defaultdict(list)
    for t, blh in zip(weather.times, weather.blh):
        if blh is not None and blh > 0:
            by_day[t.astimezone(MYT).date()].append((t, blh))
    factors = {}
    for values in by_day.values():
        if len(values) < 18:
            continue
        mean_blh = sum(b for _, b in values) / len(values)
        raw = {t: min(max((b / mean_blh) ** -BLH_EXPONENT, FACTOR_RANGE[0]), FACTOR_RANGE[1]) for t, b in values}
        norm = sum(raw.values()) / len(raw)
        factors.update({t: f / norm for t, f in raw.items()})
    return factors


def build_path(now_hour: datetime, levels: dict[date, tuple[float, float, float]],
               weather: HourlyWeather | None, anchor: float | None) -> HourlyPath:
    times = [now_hour + timedelta(hours=h) for h in range(HORIZON_H)]
    factors = diurnal_factors(weather)
    rain = dict(zip(weather.times, weather.precip)) if weather else {}
    path = HourlyPath(times, [], [], [], [])
    first = None
    for h, t in enumerate(times):
        low, mid, high = _level(t, levels)
        mid = max(mid, 0.1)
        factor = factors.get(t, 1.0)
        model = mid * factor * (WASHOUT if (rain.get(t) or 0.0) >= WASHOUT_MM else 1.0)
        if first is None:
            first = model
        if anchor is not None and first > 0:
            decay = math.exp(-h / ANCHOR_EFOLD_H)
            value, spread = model * (anchor / first) ** decay, 1.0 - decay
        else:
            value, spread = model, 1.0
        path.p50.append(round(value, 2))
        path.p10.append(round(value * (low / mid) ** spread, 2))
        path.p90.append(round(value * (high / mid) ** spread, 2))
        path.trapped.append(factor >= TRAPPED_FACTOR)
    return path


def official_api_path(path: HourlyPath, observed: dict[datetime, float],
                      fallback: float | None) -> tuple[list, list, list]:
    """DOE's API is a 24-hour running mean: combine observed past hours with forecast future hours."""
    start = path.times[0]
    result = []
    for series in (path.p10, path.p50, path.p90):
        values = []
        for t in path.times:
            window = []
            for back in range(24):
                u = t - timedelta(hours=back)
                if u < start or (u == start and u in observed):
                    v = observed.get(u, fallback)
                else:
                    v = series[int((u - start).total_seconds() // 3600)]
                if v is not None:
                    window.append(v)
            values.append(round(ugm3_to_api(sum(window) / len(window)), 1) if window else None)
        result.append(values)
    return tuple(result)
```

`pipeline/myhaze/model/closure.py`:

```python
"""Would MOE's published haze rules close schools? An indicator only: MOE makes the decision.

Rules as reported on 8 Oct 2026: close when the official API exceeds 180, or when it stays above
150 on three consecutive days. The two rules share days, so the indicator is max(rule A, rule B).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from ..config import MYT

SUN_TO_THU_STATES = {"Kedah", "Kelantan", "Terengganu"}
CLOSE_ABOVE = 180.0
STREAK_ABOVE = 150.0
STREAK_DAYS = 3
DECISION_HOUR = 7  # from 07:00 MYT the next school day is tomorrow at the earliest
Z80 = 1.2816


def is_school_day(day: date, state: str) -> bool:
    weekday = day.weekday()  # Monday = 0 … Sunday = 6
    return weekday in (6, 0, 1, 2, 3) if state in SUN_TO_THU_STATES else weekday <= 4


def next_school_day(now: datetime, state: str) -> date:
    local = now.astimezone(MYT)
    day = local.date()
    if local.hour >= DECISION_HOUR or not is_school_day(day, state):
        day += timedelta(days=1)
        while not is_school_day(day, state):
            day += timedelta(days=1)
    return day


def p_above(p50: float, low: float | None, high: float | None, threshold: float) -> float:
    if low is None or high is None or low <= 0 or high <= low:
        return 1.0 if p50 > threshold else 0.0
    sigma = (math.log(high) - math.log(low)) / (2 * Z80)
    z = (math.log(threshold) - math.log(max(p50, 1e-6))) / sigma
    return 0.5 * math.erfc(z / math.sqrt(2))


def _day_max_probability(times, official, day: date, threshold: float) -> float | None:
    low, mid, high = official
    hours = [i for i, t in enumerate(times) if t.astimezone(MYT).date() == day and mid[i] is not None]
    if not hours:
        return None
    i = max(hours, key=lambda j: mid[j])
    return p_above(mid[i], low[i], high[i], threshold)


def closure_indicator(state: str, now: datetime, times: list[datetime], official: tuple[list, list, list],
                      observed_daily_max: dict[date, float]) -> dict:
    day = next_school_day(now, state)
    rule_a = _day_max_probability(times, official, day, CLOSE_ABOVE)
    if rule_a is None:
        return {"school_day": day.isoformat(), "probability": None, "rule": None}
    today = now.astimezone(MYT).date()
    rule_b = 1.0
    for d in (day - timedelta(days=k) for k in range(STREAK_DAYS)):
        seen = 1.0 if (observed_daily_max.get(d) or 0.0) > STREAK_ABOVE else 0.0
        if d < today:
            rule_b *= seen
        else:
            forecast = _day_max_probability(times, official, d, STREAK_ABOVE)
            rule_b *= max(seen, forecast or 0.0)
    rule = "api_above_180" if rule_a >= rule_b else "three_days_above_150"
    return {"school_day": day.isoformat(), "probability": round(max(rule_a, rule_b), 2), "rule": rule}
```

`pipeline/myhaze/model/explain.py`:

```python
"""Plain-language reasons for a forecast, from the model's per-feature contributions."""
from __future__ import annotations

import math

from ..features import FeatureRow

FAMILIES = {
    "fires": ("upwind_fire", "fire_sumatra", "fire_kalimantan", "fire_peninsular", "fire_my_borneo", "fire_trend"),
    "rain": ("rain_mm", "wet_hours", "rain_fire_regions"),
    "wind": ("wind10_kmh", "wind120_kmh", "wind_from_sin", "wind_from_cos"),
    "persistence": ("pm_d0", "pm_d1", "pm_d2", "pm_trend", "region_pm_d0"),
}
REGION_NAMES = {"sumatra": "Sumatra", "kalimantan": "Kalimantan", "peninsular": "Peninsular Malaysia",
                "my_borneo": "Sarawak and Sabah"}
COMPASS = ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west")
MIN_EFFECT = 0.05  # on log1p(PM2.5): about a 5% change


def compass(deg: float) -> str:
    return COMPASS[int(((deg % 360) + 22.5) // 45) % 8]


def _sentence(family: str, worse: bool, row: FeatureRow, rain_window: str | None) -> str | None:
    if family == "persistence":
        return "Haze has been building over the last few days." if worse else \
            "The air has been improving over the last few days."
    if family == "fires":
        if not worse:
            return "Few fires are upwind right now."
        upwind = row.upwind_by_region or {}
        region = max(upwind, key=upwind.get) if upwind and max(upwind.values()) > 0 else None
        where = f", mainly in {REGION_NAMES[region]}," if region in REGION_NAMES else ""
        return f"Fires upwind{where} are adding smoke."
    if family == "rain":
        if worse:
            return "Little rain is expected to wash the smoke out."
        return f"Rain expected {rain_window} should help clear the air." if rain_window else \
            "Rain on the way should help clear the air."
    if family == "wind":
        s, c = row.x.get("wind_from_sin"), row.x.get("wind_from_cos")
        if s is None or c is None:
            return None
        direction = compass(math.degrees(math.atan2(s, c)))
        return f"Winds from the {direction} are carrying smoke in." if worse else \
            f"Winds from the {direction} are bringing cleaner air."
    return None


def explain(contrib: dict[str, float], row: FeatureRow, *, rain_window: str | None = None,
            trapped_window: str | None = None, limit: int = 3) -> list[str]:
    totals = {family: sum(contrib.get(f, 0.0) for f in features) for family, features in FAMILIES.items()}
    sentences: list[str] = []
    for family, effect in sorted(totals.items(), key=lambda item: -abs(item[1])):
        if abs(effect) < MIN_EFFECT or len(sentences) >= limit:
            continue
        sentence = _sentence(family, effect > 0, row, rain_window)
        if sentence:
            sentences.append(sentence)
    if trapped_window:
        sentences.append(f"Smoke is likely to be trapped near the ground {trapped_window}.")
    return sentences
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory pipeline run pytest -q 2>&1 | tail -2`
Expected: all unit tests pass (10 new).

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add -A pipeline
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(model): hourly Real Feel path, official API forecast, closure indicator, reasons

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 9: Website JSON contract, day plan, validators

**Files:**
- Create: `pipeline/myhaze/publish.py`, `pipeline/tests/test_publish.py`

**Interfaces:**
- Consumes:
  - `convert.BANDS`, `band`, `ugm3_to_api`
  - `hourly.HourlyPath`
  - `rows.Station`, `HourlyWeather`, `FireCell`
  - `config.MYT`
- Produces. This is the **Plan 3 contract**, documented in the module docstring:
  - `publish.iso(t) -> str`
  - `publish.plan_day_start(t) -> date`
  - `publish.day_plan(times, rf: list[int], now) -> list[dict]`
  - `publish.best_window(times, rf, day) -> dict | None`
  - `publish.when_phrase(t, now) -> str`
  - `publish.first_rain(weather, times, mm=1.0) -> datetime | None`
  - `publish.first_trapped(path) -> datetime | None`
  - `publish.now_block(reading, official) -> dict`
  - `publish.station_payload(station, generated_at, method, estimated, now, path, weather, official, closure, why, now_hour) -> dict`
  - `publish.latest_entry(payload, station) -> dict`
  - `publish.fires_payload(cells, generated_at) -> dict`
  - `publish.accuracy_payload(model, version, track_record) -> dict`
  - `publish.validate_station(obj)`, `publish.validate_latest(obj)` (both raise `ValueError`)
  - `publish.write_site_data(out_dir, latest, stations, extras: dict[str, object])`, which validates everything before writing anything

- [ ] **Step 1: Write the failing tests**

`pipeline/tests/test_publish.py`:

```python
from datetime import date, datetime, timedelta, timezone

import pytest

from myhaze.config import MYT
from myhaze.model.hourly import build_path, official_api_path
from myhaze.publish import (best_window, day_plan, latest_entry, now_block, station_payload, validate_latest,
                            validate_station, when_phrase, write_site_data)
from myhaze.rows import Station

NOW = datetime(2026, 10, 15, 15, tzinfo=timezone.utc)  # 23:00 MYT, Thursday
TIMES = [NOW + timedelta(hours=h) for h in range(48)]
KLANG = Station("CA21B", "Klang", "Selangor", 3.04, 101.45)


def sample_station():
    levels = {d: (40.0, 50.0, 70.0) for d in (date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 17))}
    path = build_path(NOW, levels, None, None)
    official = official_api_path(path, {}, 50.0)
    closure = {"school_day": "2026-10-16", "probability": 0.2, "rule": "api_above_180"}
    return station_payload(KLANG, NOW, "model", False, now_block((NOW, 60.0), (NOW, 120.0)), path, None, official,
                           closure, ["Fires upwind are adding smoke."], NOW)


def test_day_plan_blocks_follow_malaysia_time():
    today, tomorrow, after = day_plan(TIMES, list(range(48)), NOW)
    assert (today["label"], today["date"]) == ("today", "2026-10-15")
    assert [b["status"] for b in today["blocks"]] == ["past", "past", "forecast", "forecast"]
    assert today["blocks"][2]["worst_hour"] == "23:00"
    assert (today["blocks"][3]["start"], today["blocks"][3]["end"], today["blocks"][3]["worst_hour"]) == \
        ("00:00", "06:00", "05:00")
    assert [b["status"] for b in tomorrow["blocks"]] == ["forecast"] * 4
    assert [b["status"] for b in after["blocks"]] == ["forecast", "forecast", "forecast", "unavailable"]


def test_best_window_finds_the_longest_clean_stretch():
    start = datetime(2026, 10, 15, 16, tzinfo=timezone.utc)  # 00:00 MYT on the 16th
    times = [start + timedelta(hours=h) for h in range(48)]
    rf = [150] * 48
    for local_hour in (15, 16, 17, 18):
        rf[local_hour] = 80
    assert best_window(times, rf, date(2026, 10, 16)) == {"start": "15:00", "end": "19:00", "band": "moderate"}
    assert best_window(times, [150] * 48, date(2026, 10, 16)) is None


def test_when_phrase_reads_naturally():
    now = datetime(2026, 10, 15, 2, tzinfo=timezone.utc)  # Thu 10:00 MYT

    def at(day, hour):
        return datetime(2026, 10, day, hour, tzinfo=MYT)

    assert [when_phrase(at(15, 15), now), when_phrase(at(15, 20), now), when_phrase(at(16, 3), now),
            when_phrase(at(16, 8), now), when_phrase(at(17, 14), now)] == \
        ["this afternoon", "tonight", "overnight", "tomorrow morning", "on Saturday afternoon"]


def test_station_payload_matches_the_contract():
    payload = sample_station()
    validate_station(payload)
    assert payload["now"] == {"real_feel": payload["now"]["real_feel"], "real_feel_band": payload["now"]["real_feel_band"],
                              "pm25": 60.0, "real_feel_hour": "2026-10-15T15:00:00Z", "official_api": 120,
                              "official_band": "unhealthy", "official_hour": "2026-10-15T15:00:00Z"}
    entry = latest_entry(payload, KLANG)
    assert len(entry["next24"]) == 24 and entry["lat"] == 3.04
    validate_latest({"generated_at": "x", "stations": [entry]})


def test_invalid_data_is_never_written(tmp_path):
    good = sample_station()
    broken = dict(good, hours=good["hours"][:10])
    with pytest.raises(ValueError):
        validate_station(broken)
    with pytest.raises(ValueError):
        validate_latest({"stations": []})
    with pytest.raises(ValueError):
        write_site_data(tmp_path / "out", {"generated_at": "x", "stations": [latest_entry(good, KLANG)]}, [good, broken], {})
    assert not (tmp_path / "out").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest tests/test_publish.py -q 2>&1 | tail -3`
Expected: FAIL. A collection error for `myhaze.publish`.

- [ ] **Step 3: Write the implementation**

`pipeline/myhaze/publish.py`:

```python
"""The website's JSON files, the contract with Plan 3.

All times are ISO-8601 UTC strings ending in "Z". Bands are good | moderate | unhealthy | very_unhealthy | hazardous.

latest.json         {"generated_at", "stations": [{"id", "name", "state", "lat", "lon", "estimated", "method",
                     "now": NOW, "next24": [band x 24], "closure": CLOSURE}]}
stations/<id>.json  {"id", "name", "state", "generated_at", "estimated", "method", "now": NOW,
                     "hours": [HOUR x 48], "days": [DAY x 3], "why": [str], "closure": CLOSURE}
fires.json          {"generated_at", "cells": [[lat, lon, frp], ...]}
accuracy.json       {"version", "backtest": {...} | null, "track_record": {...}}

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

from .config import MYT
from .convert import BANDS, band, ugm3_to_api
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
    return next((t for t, trapped in zip(path.times[1:], path.trapped[1:])
                 if trapped and 5 <= t.astimezone(MYT).hour <= 10), None)


def now_block(reading: tuple[datetime, float] | None, official: tuple[datetime, float] | None) -> dict:
    rf = round(ugm3_to_api(reading[1])) if reading else None
    return {
        "real_feel": rf, "real_feel_band": band(rf) if rf is not None else None,
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
    rf = [int(round(ugm3_to_api(v))) for v in path.p50]
    rf_low = [int(round(ugm3_to_api(v))) for v in path.p10]
    rf_high = [int(round(ugm3_to_api(v))) for v in path.p90]
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
    out_dir = Path(out_dir)
    (out_dir / "stations").mkdir(parents=True, exist_ok=True)

    def dump(obj) -> str:
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)

    (out_dir / "latest.json").write_text(dump(latest), encoding="utf-8")
    for payload in stations:
        (out_dir / "stations" / f"{payload['id']}.json").write_text(dump(payload), encoding="utf-8")
    for name, obj in extras.items():
        (out_dir / name).write_text(dump(obj), encoding="utf-8")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory pipeline run pytest -q 2>&1 | tail -2`
Expected: all unit tests pass (5 new).

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add -A pipeline
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(publish): website JSON contract with 6-hour day plan, best window, validators

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Hourly forecast job

**Files:**
- Create: `pipeline/myhaze/jobs/forecast.py`, `supabase/migrations/0006_forecasts.sql`, `.github/workflows/forecast.yml`, `pipeline/tests/test_forecast_job.py`
- Modify: `pipeline/myhaze/store.py`, `pipeline/tests/test_store_integration.py`, `.gitignore` (+`site-data/`)

**Interfaces:**
- Consumes everything from Tasks 2–9.
- Produces:
  - `forecast.pm_now(observed, official_now, now_hour) -> tuple[float | None, bool]`
  - `forecast.latest_reading(observed, now_hour) -> tuple[datetime, float] | None`
  - `forecast.forecast_levels(rows, model, cams_daily, daily_pm) -> tuple[dict[str, dict[int, tuple]], dict[str, dict], dict[str, str]]`
  - `forecast.forecast_station(station, now_hour, generated_at, observed, official_now, weather, levels, method, contrib, row, observed_daily_max) -> dict | None`
  - `forecast.main(argv) -> int` (writes `site-data/`)
  - `Store.latest_obs(source, column, since) -> dict[str, tuple[datetime, float]]`
  - `Store.doe_daily_max(start: date) -> dict[tuple[str, date], float]`
  - `Store.save_forecast_runs(run_at, rows: list[tuple[str, str, datetime, list, list]]) -> int`
  - `Store.forecast_runs(since) -> list[tuple[datetime, str, datetime, list[float]]]`
  - `Store.upsert_verification(rows) -> int`
  - `Store.verification_summary(days=30) -> dict`

- [ ] **Step 1: Write the failing tests**

`pipeline/tests/test_forecast_job.py`:

```python
from datetime import datetime, timedelta, timezone

from myhaze.jobs.forecast import forecast_levels, forecast_station, pm_now
from myhaze.model.quantile import fit, to_text
from myhaze.publish import validate_station
from myhaze.rows import Station
from tests.test_quantile import rows_for

NOW = datetime(2026, 10, 15, 2, tzinfo=timezone.utc)  # 10:00 MYT
KLANG = Station("CA21B", "Klang", "Selangor", 3.04, 101.45)


def test_station_payload_without_hourly_feed_is_estimated():
    payload = forecast_station(KLANG, NOW, NOW, {}, (NOW, 150.0), None, None, "persistence", None, None, {})
    validate_station(payload)
    assert payload["estimated"] is True
    assert payload["now"]["real_feel"] is None and payload["now"]["official_api"] == 150
    assert payload["why"] == []


def test_forecast_without_a_model_falls_back_to_persistence():
    observed = {NOW - timedelta(hours=k): 60.0 for k in range(24)}
    assert pm_now(observed, None, NOW) == (60.0, True)
    levels, contribs, methods = forecast_levels(rows_for(4), None, {}, {})
    assert levels == {} and contribs == {} and set(methods.values()) == {"persistence"}
    payload = forecast_station(KLANG, NOW, NOW, observed, (NOW, 140.0), None, None, "persistence", None, None, {})
    validate_station(payload)
    assert payload["method"] == "persistence" and payload["estimated"] is False
    assert payload["hours"][0]["pm25"] == 60.0


def test_forecast_levels_use_the_shipped_model():
    rows = rows_for(240)
    texts = to_text(fit(rows, rounds=40))
    model = ({1: "model", 2: "persistence"}, {}, {1: texts})
    live = rows_for(3)
    levels, contribs, methods = forecast_levels(live, model, {}, {})
    assert set(levels["S"]) == {1} and len(levels["S"][1]) == 3
    assert "upwind_fire" in contribs["S"] and methods["S"] == "model"
```

`rows_for(n)` returns rows that all share station id `"S"`. That's fine here: `forecast_levels` keeps the last row per station.

Append to `pipeline/tests/test_store_integration.py`:

```python
def test_forecast_runs_latest_obs_and_doe_daily_max(store):
    from datetime import date

    hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    store.upsert_obs([Obs(TEST_ID, hour, "doe", api=161, param_symbol="**")])
    try:
        assert store.latest_obs("doe", "api", hour - timedelta(hours=2))[TEST_ID] == (hour, 161.0)
        local_day = (hour + timedelta(hours=8)).date()
        assert store.doe_daily_max(local_day - timedelta(days=1))[(TEST_ID, local_day)] == 161.0
        store.save_forecast_runs(hour, [(TEST_ID, "model", hour, [50.0, 51.0], [120.0, 121.0])])
        assert (hour, TEST_ID, hour, [50.0, 51.0]) in store.forecast_runs(hour - timedelta(hours=1))
        store.upsert_verification([(date(1999, 1, 6), "1-24h", 10, 9, 4, 4)])
        summary = store.verification_summary(days=100000)
        assert summary["1-24h"]["hours"] >= 10
    finally:
        store.conn.execute("delete from forecast_runs where station_id = %s", (TEST_ID,))
        store.conn.execute("delete from verification_daily where day = %s", (date(1999, 1, 6),))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest tests/test_forecast_job.py -q 2>&1 | tail -3`
Expected: FAIL. A collection error for `myhaze.jobs.forecast`.

- [ ] **Step 3: Write the implementation**

`supabase/migrations/0006_forecasts.sql`:

```sql
-- Forecast runs archived every 6 hours (hourly median PM2.5 and official API), and daily verification scores.
create table forecast_runs (
  run_at timestamptz not null,
  station_id text not null references stations (station_id),
  method text not null,
  first_valid timestamptz not null,
  pm25 real[] not null,
  official_api real[] not null,
  primary key (run_at, station_id)
);

create table verification_daily (
  day date not null,
  horizon text not null check (horizon in ('1-24h', '25-48h')),
  hours integer not null,
  band_hits integer not null,
  bad_hours integer not null,
  bad_caught integer not null,
  primary key (day, horizon)
);

alter table forecast_runs enable row level security;
alter table verification_daily enable row level security;
```

Append to `Store`:

```python
    def latest_obs(self, source: str, column: str, since: datetime) -> dict[str, tuple[datetime, float]]:
        if column not in self._SERIES_COLUMNS:
            raise ValueError(f"unsupported column {column!r}")
        rows = self.conn.execute(
            f"select distinct on (station_id) station_id, hour, {column} from obs_hourly "
            f"where source = %s and hour >= %s and {column} is not null order by station_id, hour desc",
            (source, since)).fetchall()
        return {sid: (hour, float(value)) for sid, hour, value in rows}

    def doe_daily_max(self, start: date) -> dict[tuple[str, date], float]:
        since = datetime.combine(start, datetime.min.time(), MYT)
        rows = self.conn.execute(
            "select station_id, (hour at time zone 'Asia/Kuala_Lumpur')::date as day, max(api) from obs_hourly "
            "where source = 'doe' and hour >= %s and api is not null group by 1, 2", (since,)).fetchall()
        return {(sid, day): float(value) for sid, day, value in rows}

    def save_forecast_runs(self, run_at: datetime, rows: list[tuple[str, str, datetime, list, list]]) -> int:
        known = self._known_ids()
        keep = [r for r in rows if r[0] in known]
        if keep:
            with self.conn.transaction(), self.conn.cursor() as cur:
                cur.executemany(
                    "insert into forecast_runs (run_at, station_id, method, first_valid, pm25, official_api) "
                    "values (%s, %s, %s, %s, %s, %s) on conflict (run_at, station_id) do update set "
                    "method = excluded.method, first_valid = excluded.first_valid, pm25 = excluded.pm25, "
                    "official_api = excluded.official_api", [(run_at, *r) for r in keep])
        return len(keep)

    def forecast_runs(self, since: datetime) -> list[tuple[datetime, str, datetime, list[float]]]:
        rows = self.conn.execute("select run_at, station_id, first_valid, pm25 from forecast_runs where run_at >= %s",
                                 (since,)).fetchall()
        return [(run_at, sid, first, list(values)) for run_at, sid, first, values in rows]

    def upsert_verification(self, rows: list[tuple[date, str, int, int, int, int]]) -> int:
        if rows:
            with self.conn.transaction(), self.conn.cursor() as cur:
                cur.executemany(
                    "insert into verification_daily (day, horizon, hours, band_hits, bad_hours, bad_caught) "
                    "values (%s, %s, %s, %s, %s, %s) on conflict (day, horizon) do update set hours = excluded.hours, "
                    "band_hits = excluded.band_hits, bad_hours = excluded.bad_hours, bad_caught = excluded.bad_caught",
                    rows)
        return len(rows)

    def verification_summary(self, days: int = 30) -> dict:
        rows = self.conn.execute(
            "select horizon, count(*), sum(hours), sum(band_hits), sum(bad_hours), sum(bad_caught) "
            "from verification_daily where day >= current_date - %s group by horizon", (days,)).fetchall()
        summary = {}
        for horizon, n_days, hours, hits, bad, caught in rows:
            summary[horizon] = {"days": int(n_days), "hours": int(hours),
                                "band_accuracy": round(hits / hours, 4) if hours else None,
                                "unhealthy_hours": int(bad), "pod_unhealthy": round(caught / bad, 4) if bad else None}
        return summary
```

Also add `from .config import MYT` to `store.py`'s imports.

`pipeline/myhaze/jobs/forecast.py`:

```python
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
    pm0, has_feed = pm_now(observed, official_now, now_hour)
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
    return station_payload(station, generated_at, method, not has_feed, now_block(reading, official_now), path,
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
                               cells_by_day, weather_latest)
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
```

Append `site-data/` to `.gitignore`.

`.github/workflows/forecast.yml`:

```yaml
name: forecast

on:
  schedule:
    - cron: "25 * * * *"
  workflow_dispatch:

concurrency:
  group: forecast
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  forecast:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
        with:
          enable-cache: true
          cache-dependency-glob: pipeline/uv.lock
      - name: Install
        run: uv --directory pipeline sync --frozen
      - name: Forecast
        run: uv --directory pipeline run python -m myhaze.jobs.forecast --out "$GITHUB_WORKSPACE/site-data"
        env:
          SUPABASE_DB_URL: ${{ secrets.SUPABASE_DB_URL }}
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: site-data
          path: site-data
          retention-days: 2
```

Plan 3 replaces the artifact upload with the Cloudflare deploy.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory pipeline run python -m myhaze.migrate && uv --directory pipeline run pytest -m "integration or not integration" -q 2>&1 | tail -2`
Expected: `applied: 0006_forecasts.sql`, then all pass (3 new unit tests + 1 integration test).

- [ ] **Step 5: Run the forecast for real and inspect one station**

```bash
uv --directory pipeline run python -m myhaze.jobs.forecast
python3 -I -c "
import json
d = json.load(open('/Users/ryanchuah/Claude Code/MYHaze/site-data/latest.json'))
print(len(d['stations']), 'stations; estimated:', sum(s['estimated'] for s in d['stations']))
k = json.load(open('/Users/ryanchuah/Claude Code/MYHaze/site-data/stations/CA21B.json'))
print(k['now']); print([ (b['start'], b['band'], b['worst_hour']) for b in k['days'][1]['blocks'] ]); print(k['why']); print(k['closure'])
"
```

Expected:
- `forecast: 68 stations written …`.
- About 5 stations estimated: those without an aqicn feed, plus any whose feed is down.
- Klang's `now` shows a Real Feel and the official API.
- Tomorrow has 4 blocks with bands.
- `why` holds 0–4 sentences, and `closure` has a school day.

Compare the Real Feel and official numbers with aqicn.org and DOE for the same hour: they should be in the same band. If they're not, check `calibration.json` before going on.

- [ ] **Step 6: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add -A pipeline supabase .github .gitignore
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): hourly forecast job writing the website JSON

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Daily verification (public track record)

**Files:**
- Create: `pipeline/myhaze/jobs/verify.py`, `.github/workflows/verify.yml`, `pipeline/tests/test_verify.py`

**Interfaces:**
- Consumes:
  - `Store.forecast_runs`, `upsert_verification`, `hourly_series`
  - `convert.aqicn_aqi_to_ugm3`, `ugm3_to_api`, `band`
  - `metrics.OK_BANDS`
- Produces:
  - `verify.score_runs(runs, observed: dict[str, dict[datetime, float]]) -> list[tuple[date, str, int, int, int, int]]`, with rows of `(day, horizon, hours, band_hits, bad_hours, bad_caught)`
  - CLI: `python -m myhaze.jobs.verify`

- [ ] **Step 1: Write the failing test**

`pipeline/tests/test_verify.py`:

```python
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from myhaze.jobs.verify import score_runs


def test_score_runs_compares_forecast_bands_with_what_happened():
    first = datetime(2026, 10, 15, 0, tzinfo=timezone.utc)
    runs = [(first, "S", first, [20.0] * 48)]  # moderate everywhere; hour 0 is the live anchor, not scored
    observed = {"S": {first + timedelta(hours=h): (20.0 if h < 30 else 200.0) for h in range(48)}}
    totals = defaultdict(lambda: [0, 0, 0, 0])
    for _day, horizon, hours, hits, bad, caught in score_runs(runs, observed):
        for i, v in enumerate((hours, hits, bad, caught)):
            totals[horizon][i] += v
    assert totals["1-24h"] == [24, 24, 0, 0]
    assert totals["25-48h"] == [23, 5, 18, 0]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv --directory pipeline run pytest tests/test_verify.py -q 2>&1 | tail -3`
Expected: FAIL. A collection error for `myhaze.jobs.verify`.

- [ ] **Step 3: Write the implementation**

`pipeline/myhaze/jobs/verify.py`:

```python
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
```

`.github/workflows/verify.yml`:

```yaml
name: verify

on:
  schedule:
    - cron: "30 18 * * *"  # 02:30 Malaysia time
  workflow_dispatch:

concurrency:
  group: verify
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
        with:
          enable-cache: true
          cache-dependency-glob: pipeline/uv.lock
      - name: Install
        run: uv --directory pipeline sync --frozen
      - name: Verify
        run: uv --directory pipeline run python -m myhaze.jobs.verify
        env:
          SUPABASE_DB_URL: ${{ secrets.SUPABASE_DB_URL }}
```

- [ ] **Step 4: Run all tests, then the job once**

Run: `uv --directory pipeline run pytest -m "integration or not integration" -q 2>&1 | tail -2 && uv --directory pipeline run python -m myhaze.jobs.verify`
Expected:
- All tests pass, including `test_every_github_action_is_pinned_to_a_commit_sha` across the 6 workflows.
- `verified N runs …`. N is 0 until the first 6-hourly forecast run has been archived, and the summary fills in from the day after.

- [ ] **Step 5: Commit, merge and push**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add -A pipeline .github
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): daily verification of archived forecasts for the public track record

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

After the final whole-branch review and its fixes:
1. Fast-forward `main` to `plan-2-forecast` and push.
2. Trigger `forecast.yml` and `train.yml` once with `gh workflow run`.
3. Watch both succeed (`train` may exit 1 with "cannot train yet" if the CSV exports aren't loaded).

---

## Self-review notes

- **Spec coverage:**

  | Spec | Where |
  |---|---|
  | §4 FIRMS | Task 1 |
  | §5 conversions | Task 2 |
  | §4 aqicn daily history | Task 3 |
  | §4 Open-Meteo history and live | Task 4 |
  | §6.1 features and model | Tasks 5, 7 |
  | §6.5 baselines | Task 6 |
  | §6.6 backtest and acceptance | Tasks 6, 7 |
  | §6.2 hourly shaper | Task 8 |
  | §6.3 official API | Task 8 |
  | §6.4 closure | Task 8 |
  | §6.1 explanations | Task 8 |
  | §8 day plan, best window, now/official, estimated flag (JSON) | Tasks 9, 10 |
  | §7.3 schedules | Tasks 7, 10, 11 |
  | §6.6 track record | Task 11 |
  | §7.4 failure handling (fallbacks, validation before publish) | Tasks 9, 10 |

- **Left to Plan 3:**
  - rendering, the sensitive-child wording, the advice text, the map, the About and accuracy pages;
  - the Cloudflare deploy that replaces the artifact upload.
- **Owner-dependent steps:**
  - Task 1 Step 6: FIRMS key.
  - Task 2 Step 6: needs 24 hours of archive.
  - Tasks 3 Step 5 and 7 Step 6: aqicn CSV exports.

  Each is written so the pipeline still runs, with honest fallbacks, if it hasn't happened yet.
