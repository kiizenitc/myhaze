# MYHaze Plan 1: Hourly Archive — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Start archiving the data that disappears: DOE's official hourly API (DOE keeps about 7 days), aqicn's hourly readings (no downloadable history) and CAMS forecasts. Everything goes into Supabase every 15 minutes from GitHub Actions, today.

**Architecture:** A small Python package, `pipeline/myhaze`, with one module per source. Each source has pure `parse_*` functions (tested against trimmed real payloads) and thin `fetch_*` wrappers over a shared retrying HTTP helper. A `Store` class writes idempotent upserts to Supabase Postgres through the session pooler. One job, `myhaze.jobs.archive`, orchestrates the sources, skips work that's already stored, records every run in `run_log`, and fails loudly only when both air-quality sources are down. A GitHub Actions cron runs it at :05, :20, :35 and :50.

**Tech Stack:** Python 3.12 (managed by uv), httpx, psycopg 3, pytest; Supabase Postgres (free tier); GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-15-myhaze-design.md`

**This is plan 1 of 3.**
- **Plan 2, forecast engine:** FIRMS ingestion and backfill, conversions, features, model, backtest, publish JSON.
- **Plan 3, website and Cloudflare deploy.**

Plans 2 and 3 are written while this archive runs.

## Global Constraints

- Python 3.12, with dependencies managed by uv. Runtime dependencies are limited to `httpx` and `psycopg[binary]`; `pytest` is dev-only.
- Licence: **AGPL-3.0**. No code or data is copied from `herr-hollis/Malaysia-Haze-Monitor` (it has no licence).
- Secrets (`AQICN_TOKEN`, `SUPABASE_DB_URL`) live only in the process environment, the git-ignored `.env`, and GitHub encrypted secrets. They never appear in code, fixtures, logs, `run_log`, exception messages or commits.
- **Archived aqicn data is never redistributed** (aqicn terms). Every table has row-level security on, with no policies.
- All stored timestamps are `timestamptz` in UTC, on the hour. DOE timestamps are naive Malaysia time (UTC+8).
- HTTP User-Agent: `MYHaze/0.1 (+https://github.com/kiizenitc/myhaze)`. Pause 0.5 s between DOE requests, and don't call DOE again once the current hour is stored.
- Commits are authored as the GitHub noreply address of `kiizenitc`, and every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

### Deliberate changes from the spec (reasons)

- **Forecast weather is not archived** (the spec had a `weather_fcst` table). Open-Meteo's historical-forecast API serves past forecasts on demand, and archiving them would take about 700 MB/year, more than the 500 MB free tier.
- **A 15-minute GitHub cron replaces the `pg_cron` trigger.** Four chances per hour give the same reliability without an extra GitHub token, and the idempotent skips keep API use low.
- **The package lives at `pipeline/myhaze/...`** rather than `pipeline/sources/...`, because Python needs a package name.
- **FIRMS ingestion moves to Plan 2.** Its history can be downloaded at any time, and the MAP_KEY isn't registered yet.
- **CAMS is archived every 6 hours, not every 3.** CAMS itself only updates twice a day.
- **`obs_hourly` stores raw source values** (US AQI and so on). Conversion to µg/m³ and API happens in Plan 2, where the conversion tables are verified.

## Review Focus

1. **Bad DOE rows.** DOE rows with `API` null, negative or a string, or for a station missing from the station list, must be skipped without crashing or failing the whole batch on a foreign key. Pinned in Task 3 (`test_parse_hourly_…`), Task 6 (`test_upsert_obs_is_idempotent_and_skips_unknown_stations`) and Task 7 (`unknown_station` count).
2. **One aqicn station offline** (`aqi: "-"`, `status: "error"` or HTTP 500) must still let every other station be archived; the run is marked partial, not failed. Pinned in Task 4 (offline/error tests) and Task 7 (`test_one_failing_aqicn_station_does_not_block_the_others`).
3. **API keys in error text.** A key in a query string or URL path must never show up in exception text, `run_log` or printed output. Pinned in Task 2 (`test_get_json_error_hides_url_and_query`) and Task 7 (`"tok123" not in str(result.details)`).
4. **Repeated or overlapping runs** (every 15 minutes, plus manual dispatches) must produce no duplicate rows and make no extra API calls once the hour is stored. Pinned in Task 6 (idempotent upsert) and Task 7 (`test_second_run_in_the_same_hour_makes_no_requests`). The workflow `concurrency` group serialises runs.
5. **Time zones.** DOE's naive Malaysia time, aqicn's `+08:00` ISO and Open-Meteo's GMT must all land on the correct UTC hour: DOE `2026-10-15T00:00:00` is `2026-10-14T16:00Z`. Pinned in Tasks 3, 4 and 5.

---

## File structure

```
pipeline/
  pyproject.toml           project, dependencies, pytest config
  .python-version          3.12
  uv.lock                  generated by uv, committed
  myhaze/
    __init__.py
    config.py              constants (MYT, USER_AGENT, REPO_ROOT), .env loading, Settings
    http.py                make_client, get_json (retries, secret-safe errors), FetchError
    rows.py                Station, Obs, CamsForecast records
    sources/
      __init__.py
      doe.py               DOE MyEQMS: stations, state ids, hourly official API
      aqicn.py             aqicn: Malaysian stations, DOE matching, hourly feed
      openmeteo.py         Open-Meteo CAMS PM2.5 forecasts, 6-hour slots
    store.py               Store: Supabase Postgres reads and upserts
    migrate.py             applies supabase/migrations/*.sql once each
    jobs/
      __init__.py
      archive.py           the 15-minute archive job (CLI: python -m myhaze.jobs.archive)
  tests/
    __init__.py
    conftest.py            disables retry sleeps in tests
    fixtures.py            trimmed real payloads
    fakes.py               FakeStore (in-memory Store)
    test_config.py
    test_http.py
    test_doe.py
    test_aqicn.py
    test_openmeteo.py
    test_store_integration.py   (marked integration; uses the real Supabase)
    test_archive_job.py
supabase/migrations/0001_archive.sql
.github/workflows/archive.yml
.github/workflows/ci.yml
LICENSE
README.md
```

All commands run from the repo root `/Users/ryanchuah/Claude Code/MYHaze`, using `uv --directory pipeline …` so they work regardless of the shell's working directory.

---

### Task 1: Toolchain, project skeleton, config

**Files:**
- Create: `pipeline/pyproject.toml`, `pipeline/.python-version`, `pipeline/myhaze/__init__.py`, `pipeline/myhaze/sources/__init__.py`, `pipeline/myhaze/jobs/__init__.py`, `pipeline/tests/__init__.py`, `pipeline/myhaze/config.py`, `pipeline/tests/test_config.py`, `LICENSE`, `README.md`
- Modify: git author of the existing first commit

**Interfaces:**
- Produces:
  - `myhaze.config.MYT` (tzinfo, UTC+8)
  - `USER_AGENT: str`
  - `REPO_ROOT: Path`
  - `Settings(aqicn_token: str | None, db_url: str | None)`
  - `load_dotenv(path: Path) -> None`
  - `load_settings(env_file: Path | None = None) -> Settings`

- [ ] **Step 1: Install uv and confirm the privacy-safe git identity**

The repo-local identity was already set to the GitHub noreply address while writing this plan, and the earlier commits were re-authored with it.

```bash
brew install uv && uv --version
git -C "/Users/ryanchuah/Claude Code/MYHaze" config user.email
git -C "/Users/ryanchuah/Claude Code/MYHaze" log --format='%ae' | sort -u
```

Expected: uv prints a version. Both git commands show only `227090317+kiizenitc@users.noreply.github.com`, so the personal Gmail address is not in history before anything goes public.

- [ ] **Step 2: Create the project files**

`pipeline/pyproject.toml`:

```toml
[project]
name = "myhaze"
version = "0.1.0"
description = "MYHaze data pipeline: archive, forecast and publish Malaysian haze data"
requires-python = ">=3.12,<3.13"
license = "AGPL-3.0-only"
dependencies = [
    "httpx>=0.27,<1",
    "psycopg[binary]>=3.2,<4",
]

[dependency-groups]
dev = ["pytest>=8"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["myhaze"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
markers = ["integration: talks to the real Supabase database (needs SUPABASE_DB_URL)"]
addopts = "-m 'not integration'"
```

`pipeline/.python-version`:

```
3.12
```

`pipeline/myhaze/__init__.py`:

```python
"""MYHaze data pipeline."""
```

`pipeline/myhaze/sources/__init__.py`:

```python
"""One module per external data source."""
```

`pipeline/myhaze/jobs/__init__.py`:

```python
"""Runnable jobs (python -m myhaze.jobs.<name>)."""
```

`pipeline/tests/__init__.py`: empty file.

- [ ] **Step 3: Write the failing test**

`pipeline/tests/test_config.py`:

```python
import os

from myhaze.config import load_settings


def test_env_file_fills_gaps_but_never_overrides_the_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# local secrets\n"
        "AQICN_TOKEN=from_file\n"
        "SUPABASE_DB_URL=\n"
        "MYHAZE_TEST_QUOTED='quoted value'\n"
    )
    monkeypatch.setenv("AQICN_TOKEN", "from_env")
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.setenv("MYHAZE_TEST_QUOTED", "placeholder")
    monkeypatch.delenv("MYHAZE_TEST_QUOTED")  # registers cleanup for the value the loader sets

    settings = load_settings(env_file)

    assert settings.aqicn_token == "from_env"
    assert settings.db_url is None
    assert os.environ["MYHAZE_TEST_QUOTED"] == "quoted value"
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `uv --directory pipeline run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'myhaze.config'`. uv downloads Python 3.12, creates `pipeline/.venv`, and writes `pipeline/uv.lock` on this first run.

- [ ] **Step 5: Write the implementation**

`pipeline/myhaze/config.py`:

```python
"""Settings and constants shared by every pipeline job."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta, timezone
from pathlib import Path

MYT = timezone(timedelta(hours=8), "MYT")
USER_AGENT = "MYHaze/0.1 (+https://github.com/kiizenitc/myhaze)"
REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    aqicn_token: str | None
    db_url: str | None


def load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines into os.environ without overriding values already set."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if value and key not in os.environ:
            os.environ[key] = value


def load_settings(env_file: Path | None = None) -> Settings:
    load_dotenv(env_file or REPO_ROOT / ".env")
    return Settings(
        aqicn_token=os.environ.get("AQICN_TOKEN") or None,
        db_url=os.environ.get("SUPABASE_DB_URL") or None,
    )
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv --directory pipeline run pytest tests/test_config.py -v`
Expected: PASS (1 passed).

- [ ] **Step 7: Add the licence and README**

```bash
gh api licenses/agpl-3.0 --jq .body > "/Users/ryanchuah/Claude Code/MYHaze/LICENSE" && head -3 "/Users/ryanchuah/Claude Code/MYHaze/LICENSE"
```

Expected: `GNU AFFERO GENERAL PUBLIC LICENSE` / `Version 3, 19 November 2007`.

`README.md`:

````markdown
# MYHaze

A free website that gives Malaysian parents a 48-hour "Real Feel" of the haze at every DOE air-quality station, so they can plan their children's day.

**Status:** being built. The hourly data archive runs first; the forecast and website follow.

## How it works so far

Every 15 minutes a GitHub Actions job archives these into a private Supabase database:

- DOE's official Air Pollutant Index for every station. DOE's public feed only keeps about 7 days.
- aqicn's hourly readings from DOE's monitors.
- CAMS PM2.5 forecasts from Open-Meteo, every 6 hours.

Design: [docs/superpowers/specs/2026-10-15-myhaze-design.md](docs/superpowers/specs/2026-10-15-myhaze-design.md)

## Run locally

```bash
brew install uv
cp .env.example .env   # then fill in AQICN_TOKEN and SUPABASE_DB_URL
uv --directory pipeline run pytest
uv --directory pipeline run python -m myhaze.migrate
uv --directory pipeline run python -m myhaze.jobs.archive
```

## Data credits

- Department of Environment Malaysia (DOE), MyEQMS / APIMS
- World Air Quality Index Project ([aqicn.org](https://aqicn.org)), relaying DOE data
- [Open-Meteo](https://open-meteo.com) (CC BY 4.0), with CAMS air-quality forecasts from Copernicus/ECMWF

Archived aqicn data is never redistributed, as aqicn's terms require.

## Licence

AGPL-3.0. See [LICENSE](LICENSE).
````

- [ ] **Step 8: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add pipeline LICENSE README.md
git -C "/Users/ryanchuah/Claude Code/MYHaze" status --short
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): project skeleton, settings loader, AGPL licence

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Expected: `status` lists `pipeline/uv.lock` and the new files, and **does not** list `.env` or `pipeline/.venv`.

---

### Task 2: Retrying HTTP helper with secret-safe errors

**Files:**
- Create: `pipeline/myhaze/http.py`, `pipeline/tests/conftest.py`, `pipeline/tests/test_http.py`

**Interfaces:**
- Consumes: `myhaze.config.USER_AGENT`
- Produces:
  - `FetchError(RuntimeError)`
  - `make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client`
  - `get_json(client, url, params=None, *, label=None, attempts=3, backoff_s=2.0)`, which returns the decoded JSON or raises `FetchError("<label or host> failed after N attempts: HTTP 503 | <ExceptionName>")`
  - Retries call `time.sleep` through the `time` module, so tests can patch `myhaze.http.time.sleep`.

- [ ] **Step 1: Write the failing tests**

`pipeline/tests/conftest.py`:

```python
import pytest


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    """Retries and DOE politeness pauses must not slow the test suite."""
    monkeypatch.setattr("myhaze.http.time.sleep", lambda seconds: None)
```

`pipeline/tests/test_http.py`:

```python
import httpx
import pytest

from myhaze.http import FetchError, get_json, make_client


def client_for(handler):
    return make_client(transport=httpx.MockTransport(handler))


def test_get_json_retries_until_success():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json={"ok": True})

    assert get_json(client_for(handler), "https://x.test/a") == {"ok": True}
    assert len(calls) == 3


def test_get_json_retries_on_html_instead_of_json():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, text="<html>maintenance</html>")
        return httpx.Response(200, json=[1])

    assert get_json(client_for(handler), "https://x.test/a") == [1]


def test_get_json_error_hides_url_and_query():
    def handler(request):
        return httpx.Response(500)

    with pytest.raises(FetchError) as info:
        get_json(client_for(handler), "https://x.test/api/SECRETPATH/data",
                 params={"token": "SECRET123"}, label="FIRMS area")
    message = str(info.value)
    assert message == "FIRMS area failed after 3 attempts: HTTP 500"
    assert info.value.__cause__ is None and info.value.__suppress_context__


def test_get_json_defaults_label_to_host():
    with pytest.raises(FetchError) as info:
        get_json(client_for(lambda r: httpx.Response(404)), "https://x.test/feed/@1/?token=abc")
    assert str(info.value) == "x.test failed after 3 attempts: HTTP 404"


def test_requests_carry_the_myhaze_user_agent():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers["user-agent"]
        return httpx.Response(200, json={})

    get_json(client_for(handler), "https://x.test/")
    assert seen["ua"].startswith("MYHaze/0.1")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest tests/test_http.py -v`
Expected: FAIL with errors importing `myhaze.http` (`ModuleNotFoundError`).

- [ ] **Step 3: Write the implementation**

`pipeline/myhaze/http.py`:

```python
"""HTTP GET with retries. Error messages never include URLs or query strings (they can hold API keys)."""
from __future__ import annotations

import time
from urllib.parse import urlsplit

import httpx

from .config import USER_AGENT


class FetchError(RuntimeError):
    """A source could not be fetched or returned something unusable."""


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        transport=transport,
    )


def _describe(exc: Exception | None) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


def get_json(client: httpx.Client, url: str, params: dict | None = None, *,
             label: str | None = None, attempts: int = 3, backoff_s: float = 2.0):
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(backoff_s * (attempt + 1))
    name = label or urlsplit(url).netloc
    raise FetchError(f"{name} failed after {attempts} attempts: {_describe(last)}") from None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory pipeline run pytest -v`
Expected: PASS (6 passed: 5 in `test_http.py`, 1 in `test_config.py`).

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add pipeline/myhaze/http.py pipeline/tests/conftest.py pipeline/tests/test_http.py
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): retrying HTTP helper that never leaks keys in errors

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Row records and the DOE source

**Files:**
- Create: `pipeline/myhaze/rows.py`, `pipeline/myhaze/sources/doe.py`, `pipeline/tests/fixtures.py`, `pipeline/tests/test_doe.py`

**Interfaces:**
- Consumes:
  - `myhaze.config.MYT`
  - `myhaze.http.get_json`, `FetchError`
- Produces:
  - `myhaze.rows.Station(station_id, name, state, lat, lon)`
  - `myhaze.rows.Obs(station_id, hour, source, api=None, param_symbol=None, pm25_aqi=None, pm10_aqi=None, o3_aqi=None, no2_aqi=None, so2_aqi=None, co_aqi=None, temp_c=None, rh=None, wind=None, pressure=None)`
  - `myhaze.rows.CamsForecast(station_id, issued_slot, first_valid, pm25: list[float | None])`
  - `doe.parse_stations(payload) -> list[Station]`
  - `doe.parse_hourly(payload) -> list[Obs]`
  - `doe.fetch_stations(client) -> list[Station]`
  - `doe.fetch_state_ids(client) -> list[int]`
  - `doe.fetch_hourly(client, state_id: int, at: datetime) -> list[Obs]` (returns the 24-hour window ending at `at`'s Malaysia hour)

- [ ] **Step 1: Write the fixtures and failing tests**

`pipeline/tests/fixtures.py`:

```python
"""Small payloads shaped exactly like real API responses (October 2026), trimmed to a few stations."""

DOE_STATIONS = {"data": [
    {"ID": 1, "STATE_ID": 9, "STATE_NAME": "Perlis", "STATION_STATUS": 1, "STATION_ID": "CA01R",
     "STATION_LOCATION": "Kangar, PERLIS", "LONGITUDE": 100.210937, "LATITUDE": 6.429928,
     "API": 56, "PARAM_SYMBOL": "**", "CLASS": "Moderate", "RECORD_DT": "2026-10-15T07:00:00"},
    {"ID": 66, "STATE_ID": 10, "STATE_NAME": "Selangor", "STATION_STATUS": 1, "STATION_ID": "MCAQM001",
     "STATION_LOCATION": "JOHAN SETIA", "LONGITUDE": 101.47, "LATITUDE": 2.98,
     "API": 160, "PARAM_SYMBOL": "**", "CLASS": "Unhealthy", "RECORD_DT": "2026-10-15T07:00:00"},
    {"ID": 99, "STATION_ID": "CA98X", "STATION_LOCATION": "Broken, NOWHERE",
     "LATITUDE": None, "LONGITUDE": None},
]}

DOE_STATELIST = [
    {"STATE_ID": 9, "STATE_NAME": "Perlis"},
    {"STATE_ID": 10, "STATE_NAME": "Selangor"},
]

DOE_HOURLY = {"api_table_hourly": [
    {"STATION_ID": "CA01R", "STATE_ID": 9, "STATION_LOCATION": "Kangar, PERLIS",
     "DATETIME": "2026-10-15T00:00:00", "API": 57, "PARAM_SYMBOL": "**"},
    {"STATION_ID": "CA01R", "STATE_ID": 9, "DATETIME": "2026-10-15T01:00:00", "API": None, "PARAM_SYMBOL": None},
    {"STATION_ID": "CA01R", "STATE_ID": 9, "DATETIME": "2026-10-15T02:00:00", "API": -1, "PARAM_SYMBOL": ""},
    {"STATION_ID": "CA01R", "STATE_ID": 9, "DATETIME": "2026-10-15T03:00:00", "API": "62", "PARAM_SYMBOL": "**"},
]}

DOE_HOURLY_NOW = {"api_table_hourly": [
    {"STATION_ID": "CA01R", "STATE_ID": 9, "DATETIME": "2026-10-15T08:00:00", "API": 56, "PARAM_SYMBOL": "**"},
    {"STATION_ID": "MCAQM001", "STATE_ID": 10, "DATETIME": "2026-10-15T08:00:00", "API": 160, "PARAM_SYMBOL": "**"},
    {"STATION_ID": "CA99X", "STATE_ID": 10, "DATETIME": "2026-10-15T08:00:00", "API": 90, "PARAM_SYMBOL": "**"},
]}
```

`pipeline/tests/test_doe.py`:

```python
from datetime import datetime, timezone

import httpx
import pytest

from myhaze.http import FetchError, make_client
from myhaze.sources import doe
from tests import fixtures


def client_returning(payload, seen=None):
    def handler(request):
        if seen is not None:
            seen.update(dict(request.url.params))
        return httpx.Response(200, json=payload)
    return make_client(transport=httpx.MockTransport(handler))


def test_parse_stations_keeps_valid_rows_and_tidies_names():
    stations = doe.parse_stations(fixtures.DOE_STATIONS)
    assert [(s.station_id, s.name, s.state) for s in stations] == [
        ("CA01R", "Kangar", "Perlis"),
        ("MCAQM001", "Johan Setia", "Selangor"),
    ]
    assert (stations[0].lat, stations[0].lon) == (6.429928, 100.210937)


def test_parse_hourly_converts_myt_to_utc_and_drops_missing_values():
    rows = doe.parse_hourly(fixtures.DOE_HOURLY)
    assert [(r.station_id, r.hour, r.api) for r in rows] == [
        ("CA01R", datetime(2026, 10, 14, 16, tzinfo=timezone.utc), 57),
        ("CA01R", datetime(2026, 10, 14, 19, tzinfo=timezone.utc), 62),
    ]
    assert all(r.source == "doe" and r.param_symbol == "**" for r in rows)


def test_fetch_hourly_asks_for_the_malaysia_hour():
    seen = {}
    at = datetime(2026, 10, 15, 0, 30, tzinfo=timezone.utc)  # 08:30 in Malaysia
    doe.fetch_hourly(client_returning(fixtures.DOE_HOURLY, seen), 14, at)
    assert seen == {"stateid": "14", "datetime": "2026-10-15T08:00:00"}


def test_fetch_state_ids_reads_the_state_list():
    assert doe.fetch_state_ids(client_returning(fixtures.DOE_STATELIST)) == [9, 10]


def test_fetch_state_ids_rejects_an_unexpected_shape():
    with pytest.raises(FetchError):
        doe.fetch_state_ids(client_returning({"oops": 1}))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest tests/test_doe.py -v`
Expected: FAIL with `ImportError` for `myhaze.sources.doe`.

- [ ] **Step 3: Write the implementation**

`pipeline/myhaze/rows.py`:

```python
"""Plain records passed between sources, the store and jobs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Station:
    station_id: str
    name: str
    state: str
    lat: float
    lon: float


@dataclass(frozen=True)
class Obs:
    """One hourly observation from one source. `hour` is timezone-aware UTC, on the hour."""
    station_id: str
    hour: datetime
    source: str
    api: int | None = None
    param_symbol: str | None = None
    pm25_aqi: int | None = None
    pm10_aqi: int | None = None
    o3_aqi: float | None = None
    no2_aqi: float | None = None
    so2_aqi: float | None = None
    co_aqi: float | None = None
    temp_c: float | None = None
    rh: float | None = None
    wind: float | None = None
    pressure: float | None = None


@dataclass(frozen=True)
class CamsForecast:
    """CAMS hourly PM2.5 (µg/m³) at a station, as fetched in one 6-hour slot."""
    station_id: str
    issued_slot: datetime
    first_valid: datetime
    pm25: list[float | None]
```

`pipeline/myhaze/sources/doe.py`:

```python
"""DOE MyEQMS public API: station list and hourly official API readings."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..config import MYT
from ..http import FetchError, get_json
from ..rows import Obs, Station

BASE = "https://eqms.doe.gov.my/api3/publicportalapims/"


def _name(location: str) -> str:
    name = location.split(",")[0].strip()
    return name.title() if name.isupper() else name


def _api_value(raw) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _utc_hour(naive_myt: str) -> datetime:
    local = datetime.fromisoformat(naive_myt).replace(tzinfo=MYT)
    return local.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def parse_stations(payload: dict) -> list[Station]:
    stations = []
    for row in payload.get("data") or []:
        try:
            stations.append(Station(
                station_id=str(row["STATION_ID"]).strip(),
                name=_name(str(row.get("STATION_LOCATION") or row["STATION_ID"])),
                state=str(row.get("STATE_NAME") or "").strip(),
                lat=float(row["LATITUDE"]),
                lon=float(row["LONGITUDE"]),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return stations


def parse_hourly(payload: dict) -> list[Obs]:
    rows = []
    for row in payload.get("api_table_hourly") or []:
        api = _api_value(row.get("API"))
        station_id = str(row.get("STATION_ID") or "").strip()
        if api is None or not station_id or not row.get("DATETIME"):
            continue
        try:
            hour = _utc_hour(row["DATETIME"])
        except ValueError:
            continue
        rows.append(Obs(station_id=station_id, hour=hour, source="doe", api=api,
                        param_symbol=row.get("PARAM_SYMBOL") or None))
    return rows


def fetch_stations(client: httpx.Client) -> list[Station]:
    return parse_stations(get_json(client, BASE + "mapcaqm", label="DOE mapcaqm"))


def fetch_state_ids(client: httpx.Client) -> list[int]:
    payload = get_json(client, BASE + "statelist", label="DOE statelist")
    try:
        return [int(state["STATE_ID"]) for state in payload]
    except (KeyError, TypeError, ValueError) as exc:
        raise FetchError(f"DOE statelist: unexpected shape ({type(exc).__name__})") from None


def fetch_hourly(client: httpx.Client, state_id: int, at: datetime) -> list[Obs]:
    stamp = at.astimezone(MYT).strftime("%Y-%m-%dT%H:00:00")
    payload = get_json(client, BASE + "apitablehourly",
                       params={"stateid": state_id, "datetime": stamp}, label="DOE apitablehourly")
    return parse_hourly(payload)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory pipeline run pytest -v`
Expected: PASS (11 passed).

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add pipeline/myhaze/rows.py pipeline/myhaze/sources/doe.py pipeline/tests/fixtures.py pipeline/tests/test_doe.py
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): DOE source for stations and hourly official API

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: aqicn source (stations, DOE matching, hourly feed)

**Files:**
- Create: `pipeline/myhaze/sources/aqicn.py`, `pipeline/tests/test_aqicn.py`
- Modify: `pipeline/tests/fixtures.py` (append)

**Interfaces:**
- Consumes:
  - `myhaze.http.get_json`, `FetchError`
  - `myhaze.rows.Station`, `Obs`
- Produces:
  - `aqicn.AqicnStation(uid, name, lat, lon)`
  - `aqicn.haversine_km(lat1, lon1, lat2, lon2) -> float`
  - `aqicn.parse_bounds(payload) -> list[AqicnStation]` (Malaysian stations only)
  - `aqicn.match_stations(stations: list[Station], candidates: list[AqicnStation], max_km=10.0) -> dict[str, tuple[int, float]]` (station id → (uid, km); each uid used at most once, nearest pairs first)
  - `aqicn.parse_feed(payload, station_id) -> Obs | None`
  - `aqicn.fetch_bounds(client, token) -> list[AqicnStation]`
  - `aqicn.fetch_feed(client, token, uid, station_id) -> Obs | None`

- [ ] **Step 1: Append fixtures and write the failing tests**

Append to `pipeline/tests/fixtures.py`:

```python
AQICN_BOUNDS = {"status": "ok", "data": [
    {"lat": 6.429928, "lon": 100.210937, "uid": 3001, "aqi": "56",
     "station": {"name": "Kangar, Perlis, Malaysia", "time": "2026-10-15T09:00:00+09:00"}},
    {"lat": 1.3521, "lon": 103.8198, "uid": 5555, "aqi": "80",
     "station": {"name": "Central, Singapore", "time": "2026-10-15T09:00:00+09:00"}},
    {"lat": 4.5841, "lon": 101.0829, "uid": 4004, "aqi": "120",
     "station": {"name": "Ipoh, Perak, Malaysia", "time": "2026-10-15T09:00:00+09:00"}},
]}

AQICN_FEED_KANGAR = {"status": "ok", "data": {
    "idx": 3001, "aqi": 56, "dominentpol": "",
    "time": {"s": "2026-10-15 08:00:00", "tz": "+08:00", "v": 1792051200, "iso": "2026-10-15T08:00:00+08:00"},
    "city": {"name": "Kangar, Perlis, Malaysia", "geo": [6.429928, 100.210937]},
    "iaqi": {"co": {"v": 0.1}, "h": {"v": 94}, "no2": {"v": 8}, "o3": {"v": 2.3}, "p": {"v": 1011},
             "pm10": {"v": 52}, "pm25": {"v": 130}, "so2": {"v": 1.7}, "t": {"v": 25}, "w": {"v": 1}},
    "forecast": {"daily": {}},
}}

AQICN_FEED_OFFLINE = {"status": "ok", "data": {
    "idx": 4004, "aqi": "-", "time": {"iso": "2026-10-15T08:00:00+08:00"}, "iaqi": {}}}

AQICN_FEED_ERROR = {"status": "error", "data": "Unknown station"}
```

`pipeline/tests/test_aqicn.py`:

```python
from datetime import datetime, timezone

import httpx
import pytest

from myhaze.http import FetchError, make_client
from myhaze.rows import Station
from myhaze.sources import aqicn
from tests import fixtures

KANGAR = Station("CA01R", "Kangar", "Perlis", 6.429928, 100.210937)
IPOH_DOE = Station("CA10A", "Jalan Tasek", "Perak", 4.6293, 101.1157)  # about 6 km from aqicn's Ipoh point
KAPIT = Station("CA40Q", "Kapit", "Sarawak", 2.0154, 112.9365)


def test_parse_bounds_keeps_only_malaysian_stations():
    got = aqicn.parse_bounds(fixtures.AQICN_BOUNDS)
    assert [(s.uid, s.name) for s in got] == [(3001, "Kangar, Perlis, Malaysia"), (4004, "Ipoh, Perak, Malaysia")]


def test_match_stations_pairs_nearest_within_the_limit():
    got = aqicn.match_stations([KANGAR, IPOH_DOE, KAPIT], aqicn.parse_bounds(fixtures.AQICN_BOUNDS))
    assert set(got) == {"CA01R", "CA10A"}
    assert got["CA01R"] == (3001, 0.0)
    assert got["CA10A"][0] == 4004 and 4 < got["CA10A"][1] < 10


def test_match_stations_gives_each_uid_to_one_station_only():
    twin = Station("CA01X", "Kangar twin", "Perlis", 6.45, 100.22)  # about 2.5 km from Kangar
    got = aqicn.match_stations([twin, KANGAR], aqicn.parse_bounds(fixtures.AQICN_BOUNDS))
    assert got == {"CA01R": (3001, 0.0)}


def test_parse_feed_reads_official_api_and_hourly_pm25():
    obs = aqicn.parse_feed(fixtures.AQICN_FEED_KANGAR, "CA01R")
    assert obs.hour == datetime(2026, 10, 15, 0, tzinfo=timezone.utc)
    assert (obs.source, obs.api, obs.pm25_aqi, obs.pm10_aqi) == ("aqicn", 56, 130, 52)
    assert (obs.temp_c, obs.rh, obs.wind, obs.pressure, obs.co_aqi) == (25, 94, 1, 1011, 0.1)


def test_parse_feed_returns_none_when_the_station_is_offline():
    assert aqicn.parse_feed(fixtures.AQICN_FEED_OFFLINE, "CA10A") is None


def test_parse_feed_raises_on_error_status():
    with pytest.raises(FetchError) as info:
        aqicn.parse_feed(fixtures.AQICN_FEED_ERROR, "CA10A")
    assert "status 'error'" in str(info.value)


def test_fetch_feed_sends_the_token_as_a_query_parameter():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["token"] = request.url.params["token"]
        return httpx.Response(200, json=fixtures.AQICN_FEED_KANGAR)

    obs = aqicn.fetch_feed(make_client(transport=httpx.MockTransport(handler)), "tok123", 3001, "CA01R")
    assert seen == {"path": "/feed/@3001/", "token": "tok123"}
    assert obs.station_id == "CA01R"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest tests/test_aqicn.py -v`
Expected: FAIL with `ImportError` for `myhaze.sources.aqicn`.

- [ ] **Step 3: Write the implementation**

`pipeline/myhaze/sources/aqicn.py`:

```python
"""aqicn (World Air Quality Index) API: Malaysian official stations and their hourly readings.

For DOE stations, `aqi` equals DOE's official API (24-hour average) and `iaqi.pm25`
is this hour's PM2.5 as a US AQI sub-index (verified against DOE on 2026-10-15).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from ..http import FetchError, get_json
from ..rows import Obs, Station

BASE = "https://api.waqi.info"
MALAYSIA_BOUNDS = "0.8,99.5,7.5,119.5"


@dataclass(frozen=True)
class AqicnStation:
    uid: int
    name: str
    lat: float
    lon: float


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def _num(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int(value) -> int | None:
    number = _num(value)
    return None if number is None else round(number)


def _checked(payload, what: str):
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        status = payload.get("status") if isinstance(payload, dict) else None
        raise FetchError(f"aqicn {what}: status {status!r}")
    return payload.get("data")


def parse_bounds(payload: dict) -> list[AqicnStation]:
    stations = []
    for item in _checked(payload, "map/bounds") or []:
        try:
            name = str(item["station"]["name"])
            if "Malaysia" not in name:
                continue
            stations.append(AqicnStation(uid=int(item["uid"]), name=name,
                                         lat=float(item["lat"]), lon=float(item["lon"])))
        except (KeyError, TypeError, ValueError):
            continue
    return stations


def match_stations(stations: list[Station], candidates: list[AqicnStation],
                   max_km: float = 10.0) -> dict[str, tuple[int, float]]:
    pairs = sorted(
        (haversine_km(s.lat, s.lon, c.lat, c.lon), s.station_id, c.uid)
        for s in stations for c in candidates
    )
    matched: dict[str, tuple[int, float]] = {}
    used: set[int] = set()
    for km, station_id, uid in pairs:
        if km > max_km:
            break
        if station_id in matched or uid in used:
            continue
        matched[station_id] = (uid, round(km, 2))
        used.add(uid)
    return matched


def parse_feed(payload: dict, station_id: str) -> Obs | None:
    data = _checked(payload, "feed")
    if not isinstance(data, dict):
        return None
    iso = (data.get("time") or {}).get("iso")
    try:
        hour = datetime.fromisoformat(iso).astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    except (TypeError, ValueError):
        return None
    iaqi = data.get("iaqi") or {}

    def reading(key: str) -> float | None:
        return _num((iaqi.get(key) or {}).get("v"))

    api, pm25 = _int(data.get("aqi")), _int(reading("pm25"))
    if api is None and pm25 is None:
        return None
    return Obs(
        station_id=station_id, hour=hour, source="aqicn", api=api, pm25_aqi=pm25,
        pm10_aqi=_int(reading("pm10")), o3_aqi=reading("o3"), no2_aqi=reading("no2"),
        so2_aqi=reading("so2"), co_aqi=reading("co"), temp_c=reading("t"), rh=reading("h"),
        wind=reading("w"), pressure=reading("p"),
    )


def fetch_bounds(client: httpx.Client, token: str) -> list[AqicnStation]:
    payload = get_json(client, f"{BASE}/map/bounds",
                       params={"latlng": MALAYSIA_BOUNDS, "networks": "official", "token": token},
                       label="aqicn map/bounds")
    return parse_bounds(payload)


def fetch_feed(client: httpx.Client, token: str, uid: int, station_id: str) -> Obs | None:
    payload = get_json(client, f"{BASE}/feed/@{uid}/", params={"token": token}, label="aqicn feed")
    return parse_feed(payload, station_id)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory pipeline run pytest -v`
Expected: PASS (18 passed).

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add pipeline/myhaze/sources/aqicn.py pipeline/tests/fixtures.py pipeline/tests/test_aqicn.py
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): aqicn source with DOE station matching and hourly feed

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Open-Meteo CAMS forecast source

**Files:**
- Create: `pipeline/myhaze/sources/openmeteo.py`, `pipeline/tests/test_openmeteo.py`
- Modify: `pipeline/tests/fixtures.py` (append)

**Interfaces:**
- Consumes:
  - `myhaze.http.get_json`, `FetchError`
  - `myhaze.rows.Station`, `CamsForecast`
- Produces:
  - `openmeteo.six_hour_slot(now: datetime) -> datetime` (UTC, floored to 00/06/12/18)
  - `openmeteo.parse_cams(payload, stations, issued_slot) -> list[CamsForecast]`
  - `openmeteo.fetch_cams(client, stations, issued_slot) -> list[CamsForecast]` (25 stations per request, 5 forecast days)

- [ ] **Step 1: Append fixtures and write the failing tests**

Append to `pipeline/tests/fixtures.py`:

```python
CAMS_TWO_STATIONS = [
    {"latitude": 6.4, "longitude": 100.2, "hourly_units": {"time": "iso8601", "pm2_5": "μg/m³"},
     "hourly": {"time": ["2026-10-15T00:00", "2026-10-15T01:00", "2026-10-15T02:00"],
                "pm2_5": [20.1, None, 22.5]}},
    {"latitude": 3.0, "longitude": 101.5, "hourly_units": {"time": "iso8601", "pm2_5": "μg/m³"},
     "hourly": {"time": ["2026-10-15T00:00", "2026-10-15T01:00", "2026-10-15T02:00"],
                "pm2_5": [61.0, 64.2, 70.9]}},
]
```

`pipeline/tests/test_openmeteo.py`:

```python
from datetime import datetime, timezone

import httpx
import pytest

from myhaze.config import MYT
from myhaze.http import FetchError, make_client
from myhaze.rows import Station
from myhaze.sources import openmeteo
from tests import fixtures

STATIONS = [Station("CA01R", "Kangar", "Perlis", 6.429928, 100.210937),
            Station("MCAQM001", "Johan Setia", "Selangor", 2.98, 101.47)]
SLOT = datetime(2026, 10, 15, 0, tzinfo=timezone.utc)


def test_six_hour_slot_floors_in_utc():
    assert openmeteo.six_hour_slot(datetime(2026, 10, 15, 13, 40, tzinfo=timezone.utc)) == \
        datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
    assert openmeteo.six_hour_slot(datetime(2026, 10, 15, 5, 0, tzinfo=MYT)) == \
        datetime(2026, 10, 14, 18, tzinfo=timezone.utc)


def test_parse_cams_maps_locations_to_stations_in_order():
    got = openmeteo.parse_cams(fixtures.CAMS_TWO_STATIONS, STATIONS, SLOT)
    assert [(c.station_id, c.first_valid, c.pm25) for c in got] == [
        ("CA01R", SLOT, [20.1, None, 22.5]),
        ("MCAQM001", SLOT, [61.0, 64.2, 70.9]),
    ]
    assert all(c.issued_slot == SLOT for c in got)


def test_parse_cams_accepts_a_single_object_for_one_station():
    got = openmeteo.parse_cams(fixtures.CAMS_TWO_STATIONS[0], STATIONS[:1], SLOT)
    assert [c.station_id for c in got] == ["CA01R"]


def test_parse_cams_rejects_a_location_count_mismatch():
    with pytest.raises(FetchError):
        openmeteo.parse_cams(fixtures.CAMS_TWO_STATIONS, STATIONS[:1], SLOT)


def test_fetch_cams_sends_coordinates_and_asks_for_gmt():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=fixtures.CAMS_TWO_STATIONS)

    got = openmeteo.fetch_cams(make_client(transport=httpx.MockTransport(handler)), STATIONS, SLOT)
    assert len(got) == 2 and len(seen) == 1
    assert seen[0]["latitude"] == "6.4299,2.9800"
    assert seen[0]["longitude"] == "100.2109,101.4700"
    assert (seen[0]["hourly"], seen[0]["timezone"], seen[0]["forecast_days"]) == ("pm2_5", "GMT", "5")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest tests/test_openmeteo.py -v`
Expected: FAIL with `ImportError` for `myhaze.sources.openmeteo`.

- [ ] **Step 3: Write the implementation**

`pipeline/myhaze/sources/openmeteo.py`:

```python
"""Open-Meteo air-quality API: CAMS PM2.5 forecasts at station points."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..http import FetchError, get_json
from ..rows import CamsForecast, Station

AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
BATCH = 25
FORECAST_DAYS = 5


def six_hour_slot(now: datetime) -> datetime:
    utc = now.astimezone(timezone.utc)
    return utc.replace(hour=utc.hour - utc.hour % 6, minute=0, second=0, microsecond=0)


def parse_cams(payload, stations: list[Station], issued_slot: datetime) -> list[CamsForecast]:
    items = payload if isinstance(payload, list) else [payload]
    if len(items) != len(stations):
        raise FetchError(f"Open-Meteo returned {len(items)} locations for {len(stations)} stations")
    forecasts = []
    for station, item in zip(stations, items):
        hourly = (item or {}).get("hourly") or {}
        times, values = hourly.get("time") or [], hourly.get("pm2_5") or []
        if not times or len(times) != len(values):
            continue
        first_valid = datetime.fromisoformat(times[0]).replace(tzinfo=timezone.utc)
        forecasts.append(CamsForecast(station.station_id, issued_slot, first_valid,
                                      [None if v is None else float(v) for v in values]))
    return forecasts


def fetch_cams(client: httpx.Client, stations: list[Station], issued_slot: datetime) -> list[CamsForecast]:
    forecasts = []
    for start in range(0, len(stations), BATCH):
        chunk = stations[start:start + BATCH]
        payload = get_json(client, AQ_URL, params={
            "latitude": ",".join(f"{s.lat:.4f}" for s in chunk),
            "longitude": ",".join(f"{s.lon:.4f}" for s in chunk),
            "hourly": "pm2_5",
            "forecast_days": FORECAST_DAYS,
            "timezone": "GMT",
        }, label="Open-Meteo air-quality")
        forecasts.extend(parse_cams(payload, chunk, issued_slot))
    return forecasts
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory pipeline run pytest -v`
Expected: PASS (23 passed).

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add pipeline/myhaze/sources/openmeteo.py pipeline/tests/fixtures.py pipeline/tests/test_openmeteo.py
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): Open-Meteo CAMS forecast source

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Supabase schema, migration runner and Store

**Files:**
- Create: `supabase/migrations/0001_archive.sql`, `pipeline/myhaze/migrate.py`, `pipeline/myhaze/store.py`, `pipeline/tests/test_store_integration.py`
- Modify: `.env` (owner adds `SUPABASE_DB_URL`; never committed)

**Interfaces:**
- Consumes:
  - `myhaze.config.REPO_ROOT`, `load_settings`
  - `myhaze.rows.Station`, `Obs`, `CamsForecast`
- Produces:
  - `migrate.apply_migrations(conn, directory=MIGRATIONS_DIR) -> list[str]`
  - `migrate.main() -> int`
  - `store.Store.connect(db_url) -> Store`
  - `store.Store` methods:
    - `close()`
    - `upsert_stations(stations, aqicn: dict[str, tuple[int, float]] | None = None) -> int` (`None` keeps the existing aqicn columns)
    - `stations() -> list[Station]`
    - `aqicn_uids() -> dict[str, int]`
    - `upsert_obs(rows: list[Obs]) -> tuple[int, int]` (written, skipped for an unknown station)
    - `latest_hours(source) -> dict[str, datetime]` (last 2 days only)
    - `count_obs_at(source, hour) -> int`
    - `cams_slot_done(slot) -> bool`
    - `upsert_cams(rows: list[CamsForecast]) -> int`
    - `log_run(job, started_at, finished_at, status, details: dict) -> None`

- [ ] **Step 1: Owner creates the Supabase project (manual, about 3 minutes)**

1. At https://supabase.com/dashboard, choose **New project**. Name it `myhaze`, set the region to **Southeast Asia (Singapore)**, generate a strong database password, and save it in your password manager.
2. Open the project, click **Connect**, choose **Session pooler**, and copy the URI. It looks like `postgresql://postgres.<ref>:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres`. Use the pooler, not the direct connection: GitHub runners only have IPv4, and the direct host is IPv6-only.
3. Put the password into the URI. Percent-encode special characters, for example `@` → `%40` and `#` → `%23`. Set it as `SUPABASE_DB_URL=` in `/Users/ryanchuah/Claude Code/MYHaze/.env`.

Verify, without printing the secret:

```bash
grep -c '^SUPABASE_DB_URL=postgresql://' "/Users/ryanchuah/Claude Code/MYHaze/.env"
```

Expected: `1`

- [ ] **Step 2: Write the migration**

`supabase/migrations/0001_archive.sql`:

```sql
-- MYHaze archive schema. Raw source values only; unit conversions happen in the forecast pipeline.
-- Row level security is on for every table and there are no policies: only the pipeline's direct
-- (table-owner) connection can read or write. aqicn's terms forbid redistributing archived data.

create table stations (
  station_id text primary key,
  name text not null,
  state text not null,
  lat double precision not null,
  lon double precision not null,
  aqicn_uid integer,
  aqicn_km real,
  active boolean not null default true,
  updated_at timestamptz not null default now()
);

create table obs_hourly (
  station_id text not null references stations (station_id),
  hour timestamptz not null,
  source text not null check (source in ('doe', 'aqicn')),
  api smallint,
  param_symbol text,
  pm25_aqi smallint,
  pm10_aqi smallint,
  o3_aqi real,
  no2_aqi real,
  so2_aqi real,
  co_aqi real,
  temp_c real,
  rh real,
  wind real,
  pressure real,
  fetched_at timestamptz not null default now(),
  primary key (station_id, hour, source)
);
create index obs_hourly_source_hour on obs_hourly (source, hour);

create table cams_fcst (
  station_id text not null references stations (station_id),
  issued_slot timestamptz not null,
  first_valid timestamptz not null,
  pm25 real[] not null,
  primary key (station_id, issued_slot)
);
create index cams_fcst_slot on cams_fcst (issued_slot);

create table run_log (
  id bigserial primary key,
  job text not null,
  started_at timestamptz not null,
  finished_at timestamptz not null,
  status text not null check (status in ('ok', 'partial', 'failed')),
  details jsonb not null
);

alter table stations enable row level security;
alter table obs_hourly enable row level security;
alter table cams_fcst enable row level security;
alter table run_log enable row level security;
```

- [ ] **Step 3: Write the failing integration tests**

These run against the real database, use the throwaway station id `ZZTEST`, and clean up after themselves.

`pipeline/tests/test_store_integration.py`:

```python
from datetime import datetime, timezone

import pytest

from myhaze.config import load_settings
from myhaze.migrate import apply_migrations
from myhaze.rows import CamsForecast, Obs, Station
from myhaze.store import Store

pytestmark = pytest.mark.integration
TEST_ID = "ZZTEST"
OLD_HOUR = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def store():
    settings = load_settings()
    if not settings.db_url:
        pytest.skip("SUPABASE_DB_URL is not set")
    s = Store.connect(settings.db_url)
    apply_migrations(s.conn)
    s.upsert_stations([Station(TEST_ID, "Test station", "Nowhere", 0.0, 0.0)])
    yield s
    for table in ("obs_hourly", "cams_fcst", "stations"):
        s.conn.execute(f"delete from {table} where station_id = %s", (TEST_ID,))
    s.conn.execute("delete from run_log where job = 'test'")
    s.close()


def test_upsert_obs_is_idempotent_and_skips_unknown_stations(store):
    assert store.upsert_obs([Obs(TEST_ID, OLD_HOUR, "doe", api=99), Obs("NOPE1", OLD_HOUR, "doe", api=1)]) == (1, 1)
    assert store.upsert_obs([Obs(TEST_ID, OLD_HOUR, "doe", api=101)]) == (1, 0)
    count, api = store.conn.execute(
        "select count(*), max(api) from obs_hourly where station_id = %s", (TEST_ID,)).fetchone()
    assert (count, api) == (1, 101)
    assert store.count_obs_at("doe", OLD_HOUR) >= 1


def test_latest_hours_reports_recent_hours_only(store):
    recent = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    store.upsert_obs([Obs(TEST_ID, OLD_HOUR, "aqicn", api=5), Obs(TEST_ID, recent, "aqicn", api=6, pm25_aqi=130)])
    assert store.latest_hours("aqicn")[TEST_ID] == recent


def test_stations_and_aqicn_mapping_roundtrip(store):
    store.upsert_stations([Station(TEST_ID, "Renamed", "Nowhere", 0.0, 0.0)], {TEST_ID: (999999, 1.25)})
    assert store.aqicn_uids()[TEST_ID] == 999999
    assert any(s.station_id == TEST_ID and s.name == "Renamed" for s in store.stations())
    store.upsert_stations([Station(TEST_ID, "Renamed", "Nowhere", 0.0, 0.0)])  # None keeps the mapping
    assert store.aqicn_uids()[TEST_ID] == 999999


def test_cams_roundtrip_keeps_missing_values(store):
    slot = datetime(2026, 1, 1, 6, tzinfo=timezone.utc)
    assert store.upsert_cams([CamsForecast(TEST_ID, slot, slot, [1.5, None, 3.0])]) == 1
    assert store.cams_slot_done(slot)
    (values,) = store.conn.execute(
        "select pm25 from cams_fcst where station_id = %s and issued_slot = %s", (TEST_ID, slot)).fetchone()
    assert values == [1.5, None, 3.0]


def test_run_log_accepts_json_details(store):
    store.log_run("test", OLD_HOUR, OLD_HOUR, "ok", {"doe": {"status": "ok", "written": 3}})
    (details,) = store.conn.execute("select details from run_log where job = 'test'").fetchone()
    assert details == {"doe": {"status": "ok", "written": 3}}


def test_every_table_has_row_level_security(store):
    rows = store.conn.execute(
        "select relname, relrowsecurity from pg_class "
        "where relnamespace = 'public'::regnamespace and relkind = 'r'").fetchall()
    assert rows and all(enabled for _, enabled in rows), rows
```

Caution: `test_stations_and_aqicn_mapping_roundtrip` writes an aqicn mapping. `upsert_stations` with a mapping clears every other station's `aqicn_uid` in the same transaction. Run the integration tests before the first live archive run (as this plan orders them), or re-run the archive job straight afterwards at minute < 15 so the station sync rebuilds the mapping.

- [ ] **Step 4: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest -m integration -v`
Expected: FAIL with `ImportError` for `myhaze.migrate` / `myhaze.store`.

- [ ] **Step 5: Write the implementation**

`pipeline/myhaze/migrate.py`:

```python
"""Apply supabase/migrations/*.sql in name order, each exactly once."""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg

from .config import REPO_ROOT, load_settings

MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"


def apply_migrations(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    conn.execute("create table if not exists schema_migrations "
                 "(name text primary key, applied_at timestamptz not null default now())")
    conn.execute("alter table schema_migrations enable row level security")
    done = {row[0] for row in conn.execute("select name from schema_migrations").fetchall()}
    applied = []
    for path in sorted(directory.glob("*.sql")):
        if path.name in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("insert into schema_migrations (name) values (%s)", (path.name,))
        applied.append(path.name)
    return applied


def main() -> int:
    settings = load_settings()
    if not settings.db_url:
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 2
    with psycopg.connect(settings.db_url, autocommit=True, prepare_threshold=None) as conn:
        applied = apply_migrations(conn)
    print("applied:", ", ".join(applied) if applied else "nothing new")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`pipeline/myhaze/store.py`:

```python
"""Supabase Postgres access for the archive (direct connection through the session pooler)."""
from __future__ import annotations

from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from .rows import CamsForecast, Obs, Station

OBS_COLUMNS = ("station_id", "hour", "source", "api", "param_symbol", "pm25_aqi", "pm10_aqi",
               "o3_aqi", "no2_aqi", "so2_aqi", "co_aqi", "temp_c", "rh", "wind", "pressure")
_OBS_UPSERT = (
    f"insert into obs_hourly ({', '.join(OBS_COLUMNS)}) "
    f"values ({', '.join(['%s'] * len(OBS_COLUMNS))}) "
    "on conflict (station_id, hour, source) do update set "
    + ", ".join(f"{c} = excluded.{c}" for c in OBS_COLUMNS[3:])
    + ", fetched_at = now()"
)


class Store:
    def __init__(self, conn: psycopg.Connection):
        self.conn = conn

    @classmethod
    def connect(cls, db_url: str) -> "Store":
        return cls(psycopg.connect(db_url, autocommit=True, prepare_threshold=None))

    def close(self) -> None:
        self.conn.close()

    def upsert_stations(self, stations: list[Station],
                        aqicn: dict[str, tuple[int, float]] | None = None) -> int:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.executemany(
                "insert into stations (station_id, name, state, lat, lon) values (%s, %s, %s, %s, %s) "
                "on conflict (station_id) do update set name = excluded.name, state = excluded.state, "
                "lat = excluded.lat, lon = excluded.lon, updated_at = now()",
                [(s.station_id, s.name, s.state, s.lat, s.lon) for s in stations],
            )
            if aqicn is not None:
                cur.execute("update stations set aqicn_uid = null, aqicn_km = null")
                cur.executemany(
                    "update stations set aqicn_uid = %s, aqicn_km = %s where station_id = %s",
                    [(uid, km, station_id) for station_id, (uid, km) in aqicn.items()],
                )
        return len(stations)

    def stations(self) -> list[Station]:
        rows = self.conn.execute(
            "select station_id, name, state, lat, lon from stations where active order by station_id").fetchall()
        return [Station(*row) for row in rows]

    def aqicn_uids(self) -> dict[str, int]:
        return dict(self.conn.execute(
            "select station_id, aqicn_uid from stations where active and aqicn_uid is not null").fetchall())

    def _known_ids(self) -> set[str]:
        return {row[0] for row in self.conn.execute("select station_id from stations").fetchall()}

    def upsert_obs(self, rows: list[Obs]) -> tuple[int, int]:
        known = self._known_ids()
        keep = [r for r in rows if r.station_id in known]
        if keep:
            with self.conn.transaction(), self.conn.cursor() as cur:
                cur.executemany(_OBS_UPSERT, [tuple(getattr(r, c) for c in OBS_COLUMNS) for r in keep])
        return len(keep), len(rows) - len(keep)

    def latest_hours(self, source: str) -> dict[str, datetime]:
        return dict(self.conn.execute(
            "select station_id, max(hour) from obs_hourly "
            "where source = %s and hour > now() - interval '2 days' group by station_id",
            (source,)).fetchall())

    def count_obs_at(self, source: str, hour: datetime) -> int:
        return self.conn.execute(
            "select count(*) from obs_hourly where source = %s and hour = %s", (source, hour)).fetchone()[0]

    def cams_slot_done(self, slot: datetime) -> bool:
        return self.conn.execute(
            "select exists (select 1 from cams_fcst where issued_slot = %s)", (slot,)).fetchone()[0]

    def upsert_cams(self, rows: list[CamsForecast]) -> int:
        known = self._known_ids()
        keep = [r for r in rows if r.station_id in known]
        if keep:
            with self.conn.transaction(), self.conn.cursor() as cur:
                cur.executemany(
                    "insert into cams_fcst (station_id, issued_slot, first_valid, pm25) values (%s, %s, %s, %s) "
                    "on conflict (station_id, issued_slot) do update set "
                    "first_valid = excluded.first_valid, pm25 = excluded.pm25",
                    [(r.station_id, r.issued_slot, r.first_valid, r.pm25) for r in keep],
                )
        return len(keep)

    def log_run(self, job: str, started_at: datetime, finished_at: datetime,
                status: str, details: dict) -> None:
        self.conn.execute(
            "insert into run_log (job, started_at, finished_at, status, details) values (%s, %s, %s, %s, %s)",
            (job, started_at, finished_at, status, Jsonb(details)),
        )
```

- [ ] **Step 6: Apply the migration and run the integration tests**

```bash
uv --directory pipeline run python -m myhaze.migrate
uv --directory pipeline run pytest -m integration -v
uv --directory pipeline run python -m myhaze.migrate
```

Expected:
- The first migrate prints `applied: 0001_archive.sql`.
- The tests PASS (6 passed).
- The second migrate prints `applied: nothing new`.

If the connection fails with a password error, the password in the URI needs percent-encoding (Step 1.3).

- [ ] **Step 7: Run the unit suite and commit**

Run: `uv --directory pipeline run pytest -v`
Expected: PASS (23 passed, 6 deselected).

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add supabase pipeline/myhaze/migrate.py pipeline/myhaze/store.py pipeline/tests/test_store_integration.py
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): Supabase archive schema with RLS, migration runner, Store

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The archive job

**Files:**
- Create: `pipeline/myhaze/jobs/archive.py`, `pipeline/tests/fakes.py`, `pipeline/tests/test_archive_job.py`

**Interfaces:**
- Consumes everything above:
  - `doe.fetch_stations`, `doe.fetch_state_ids`, `doe.fetch_hourly`
  - `aqicn.fetch_bounds`, `aqicn.match_stations`, `aqicn.fetch_feed`
  - `openmeteo.six_hour_slot`, `openmeteo.fetch_cams`
  - the `Store` methods
- Produces:
  - `archive.RunResult(status: str, details: dict)`
  - `archive.sync_stations(client, store, settings, now_utc) -> dict`
  - `archive.archive_doe(client, store, now_utc, backfill_days=0) -> dict`
  - `archive.archive_aqicn(client, store, settings, now_utc) -> dict`
  - `archive.archive_cams(client, store, now_utc) -> dict`
  - `archive.run(now_utc, settings, client, store, *, doe_backfill_days=0) -> RunResult`
  - `archive.main(argv=None) -> int` (exit code 1 only when the run status is `failed`)
- Step statuses: `ok` | `partial` | `failed` | `skipped`.
- Run status:
  - `failed` if and only if both `doe` and `aqicn` failed;
  - otherwise `partial` if any step failed or was partial;
  - otherwise `ok`.

- [ ] **Step 1: Write the fake store and the failing tests**

`pipeline/tests/fakes.py`:

```python
"""In-memory stand-in for myhaze.store.Store with the same method names and return types."""


class FakeStore:
    def __init__(self, stations=None, aqicn=None):
        self._stations = {s.station_id: s for s in (stations or [])}
        self._aqicn = dict(aqicn or {})
        self.obs = {}
        self.cams = {}
        self.runs = []

    def upsert_stations(self, stations, aqicn=None):
        for station in stations:
            self._stations[station.station_id] = station
        if aqicn is not None:
            self._aqicn = {station_id: uid for station_id, (uid, _km) in aqicn.items()}
        return len(stations)

    def stations(self):
        return sorted(self._stations.values(), key=lambda s: s.station_id)

    def aqicn_uids(self):
        return dict(self._aqicn)

    def upsert_obs(self, rows):
        keep = [r for r in rows if r.station_id in self._stations]
        for r in keep:
            self.obs[(r.station_id, r.hour, r.source)] = r
        return len(keep), len(rows) - len(keep)

    def latest_hours(self, source):
        latest = {}
        for station_id, hour, src in self.obs:
            if src == source and (station_id not in latest or hour > latest[station_id]):
                latest[station_id] = hour
        return latest

    def count_obs_at(self, source, hour):
        return sum(1 for (_, h, src) in self.obs if src == source and h == hour)

    def cams_slot_done(self, slot):
        return any(issued == slot for (_, issued) in self.cams)

    def upsert_cams(self, rows):
        keep = [r for r in rows if r.station_id in self._stations]
        for r in keep:
            self.cams[(r.station_id, r.issued_slot)] = r
        return len(keep)

    def log_run(self, job, started_at, finished_at, status, details):
        self.runs.append((job, status, details))
```

`pipeline/tests/test_archive_job.py`:

```python
from datetime import datetime, timezone

import httpx

from myhaze.config import Settings
from myhaze.http import make_client
from myhaze.jobs import archive
from myhaze.rows import Station
from tests import fixtures
from tests.fakes import FakeStore

NOW = datetime(2026, 10, 15, 0, 5, tzinfo=timezone.utc)  # 08:05 in Malaysia
HOUR = datetime(2026, 10, 15, 0, tzinfo=timezone.utc)
SETTINGS = Settings(aqicn_token="tok123", db_url="postgresql://unused")
KANGAR = Station("CA01R", "Kangar", "Perlis", 6.429928, 100.210937)
IPOH = Station("CA10A", "Jalan Tasek", "Perak", 4.6293, 101.1157)

HEALTHY = {
    "mapcaqm": fixtures.DOE_STATIONS,
    "statelist": fixtures.DOE_STATELIST,
    "apitablehourly": fixtures.DOE_HOURLY_NOW,
    "/map/bounds": fixtures.AQICN_BOUNDS,
    "/feed/@3001/": fixtures.AQICN_FEED_KANGAR,
    "/v1/air-quality": fixtures.CAMS_TWO_STATIONS,
}


def routed_client(routes, calls):
    """routes maps a URL-path suffix to a JSON payload, or to an int HTTP status."""
    def handler(request):
        calls.append(request.url.path)
        for suffix, reply in routes.items():
            if request.url.path.endswith(suffix):
                if isinstance(reply, int):
                    return httpx.Response(reply)
                return httpx.Response(200, json=reply)
        return httpx.Response(404)
    return make_client(transport=httpx.MockTransport(handler))


def test_first_run_archives_doe_aqicn_and_cams():
    store = FakeStore()
    result = archive.run(NOW, SETTINGS, routed_client(HEALTHY, []), store)

    assert result.status == "ok", result.details
    assert store.aqicn_uids() == {"CA01R": 3001}
    assert {k for k in store.obs if k[2] == "doe"} == {("CA01R", HOUR, "doe"), ("MCAQM001", HOUR, "doe")}
    assert result.details["doe"]["unknown_station"] == 1
    assert store.obs[("CA01R", HOUR, "aqicn")].pm25_aqi == 130
    assert len(store.cams) == 2
    assert store.runs[-1][:2] == ("archive", "ok")


def test_second_run_in_the_same_hour_makes_no_requests():
    store, calls = FakeStore(), []
    client = routed_client(HEALTHY, calls)
    archive.run(NOW, SETTINGS, client, store)
    first_run_calls = len(calls)

    result = archive.run(NOW.replace(minute=20), SETTINGS, client, store)

    assert len(calls) == first_run_calls
    assert {d["status"] for d in result.details.values()} == {"skipped"}
    assert result.status == "ok"


def test_one_failing_aqicn_station_does_not_block_the_others():
    store = FakeStore(stations=[KANGAR, IPOH], aqicn={"CA01R": 3001, "CA10A": 4004})
    routes = dict(HEALTHY, **{"/feed/@4004/": 500})

    result = archive.run(NOW.replace(minute=30), SETTINGS, routed_client(routes, []), store)

    assert result.details["aqicn"]["status"] == "partial"
    assert ("CA01R", HOUR, "aqicn") in store.obs
    assert "tok123" not in str(result.details)
    assert result.status == "partial"


def test_run_fails_only_when_doe_and_aqicn_are_both_down():
    store = FakeStore(stations=[KANGAR], aqicn={"CA01R": 3001})
    routes = {"statelist": 503, "/feed/@3001/": 503, "/v1/air-quality": fixtures.CAMS_TWO_STATIONS[0]}

    result = archive.run(NOW.replace(minute=30), SETTINGS, routed_client(routes, []), store)

    assert result.details["doe"]["status"] == "failed"
    assert result.details["aqicn"]["status"] == "failed"
    assert result.details["cams"]["status"] == "ok"
    assert result.status == "failed"
    assert store.runs[-1][1] == "failed"


def test_doe_backfill_requests_one_window_per_day():
    store, stamps = FakeStore(stations=[KANGAR]), []

    def handler(request):
        if request.url.path.endswith("statelist"):
            return httpx.Response(200, json=[{"STATE_ID": 9}])
        stamps.append(request.url.params["datetime"])
        return httpx.Response(200, json=fixtures.DOE_HOURLY)

    detail = archive.archive_doe(make_client(transport=httpx.MockTransport(handler)), store, NOW, backfill_days=2)

    assert stamps == ["2026-10-15T08:00:00", "2026-10-14T08:00:00", "2026-10-13T08:00:00"]
    assert (detail["status"], detail["written"]) == ("ok", 2)


def test_a_sharply_shrunken_aqicn_mapping_is_ignored():
    many = [Station(f"CA{i:02d}X", f"Station {i}", "Test", 1.0 + i, 101.0) for i in range(10)]
    store = FakeStore(stations=many, aqicn={s.station_id: 9000 + i for i, s in enumerate(many)})

    detail = archive.sync_stations(routed_client(HEALTHY, []), store, SETTINGS, NOW)

    assert "aqicn_mapping_rejected" in detail
    assert len(store.aqicn_uids()) == 10


def test_missing_token_skips_aqicn_without_failing():
    store = FakeStore(stations=[KANGAR])
    detail = archive.archive_aqicn(routed_client(HEALTHY, []), store, Settings(None, "x"), NOW)
    assert detail == {"status": "skipped", "reason": "AQICN_TOKEN not set"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv --directory pipeline run pytest tests/test_archive_job.py -v`
Expected: FAIL with `ImportError` for `myhaze.jobs.archive`.

- [ ] **Step 3: Write the implementation**

`pipeline/myhaze/jobs/archive.py`:

```python
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
AQICN_MAPPING_MIN_SHARE = 0.8


@dataclass
class RunResult:
    status: str
    details: dict = field(default_factory=dict)


def _hour(now: datetime) -> datetime:
    return now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


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


def archive_doe(client, store, now_utc: datetime, backfill_days: int = 0) -> dict:
    active = len(store.stations())
    if not backfill_days and active and store.count_obs_at("doe", _hour(now_utc)) >= DOE_UP_TO_DATE_SHARE * active:
        return {"status": "skipped", "reason": "hour already stored"}
    rows: dict = {}
    errors: list[str] = []
    for state_id in doe.fetch_state_ids(client):
        for days_back in range(backfill_days + 1):
            try:
                for obs in doe.fetch_hourly(client, state_id, now_utc - timedelta(days=days_back)):
                    rows[(obs.station_id, obs.hour)] = obs
            except FetchError as exc:
                errors.append(f"state {state_id}: {exc}")
            time.sleep(DOE_PAUSE_S)
    if not rows and not errors:
        errors.append("DOE returned no readings")
    written, unknown = store.upsert_obs(list(rows.values())) if rows else (0, 0)
    status = "ok" if not errors else ("partial" if written else "failed")
    return {"status": status, "written": written, "unknown_station": unknown,
            "errors": errors[:5], "error_count": len(errors)}


def archive_aqicn(client, store, settings, now_utc: datetime) -> dict:
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
    for station_id, uid in sorted(todo.items()):
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
    steps = {
        "stations": lambda: sync_stations(client, store, settings, now_utc),
        "doe": lambda: archive_doe(client, store, now_utc, doe_backfill_days),
        "aqicn": lambda: archive_aqicn(client, store, settings, now_utc),
        "cams": lambda: archive_cams(client, store, now_utc),
    }
    details: dict[str, dict] = {}
    for name, step in steps.items():
        try:
            details[name] = step()
        except FetchError as exc:
            details[name] = {"status": "failed", "errors": [str(exc)]}
    if details["doe"]["status"] == "failed" and details["aqicn"]["status"] == "failed":
        status = "failed"
    elif any(d["status"] in ("failed", "partial") for d in details.values()):
        status = "partial"
    else:
        status = "ok"
    store.log_run("archive", started, datetime.now(timezone.utc), status, details)
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv --directory pipeline run pytest -v`
Expected: PASS (30 passed, 6 deselected).

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add pipeline/myhaze/jobs/archive.py pipeline/tests/fakes.py pipeline/tests/test_archive_job.py
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(pipeline): idempotent 15-minute archive job with run log

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: First live run and DOE 7-day backfill (captures data that is about to expire)

**Files:** none changed. This task proves the pipeline against the real services and saves the last 7 days of DOE history before it rolls off.

**Interfaces:**
- Consumes: `python -m myhaze.jobs.archive` (Task 7) and the migrated database (Task 6).

- [ ] **Step 1: Run the job with a 7-day DOE backfill**

Run at a minute below 15 past the hour, so the station sync runs. If it's later than that, the job still archives, and the next run at :05 does the sync. Even so, run this first one before :15 if possible.

```bash
uv --directory pipeline run python -m myhaze.jobs.archive --doe-backfill-days 7
```

Expected, approximately:

```
stations  ok       stations=68, aqicn_matched=63
doe       ok       written=7000+, unknown_station=0, errors=[], error_count=0
aqicn     ok       written=63, requested=63, errors=[], error_count=0
cams      ok       written=68, slot=2026-10-15T00:00:00+00:00
run: ok
```

`aqicn_matched` should be 63, give or take a station: 5 DOE stations have no aqicn feed (`CA04K`, `CA11A`, `MCAQM001–003`). DOE `written` reflects about 7 days × 68 stations × 24 hours, less hours DOE has no value for.

- [ ] **Step 2: Verify what landed**

```bash
uv --directory pipeline run python - <<'EOF'
import psycopg
from myhaze.config import load_settings
with psycopg.connect(load_settings().db_url, prepare_threshold=None) as conn:
    for sql in [
        "select count(*), count(aqicn_uid) from stations",
        "select source, count(*), min(hour), max(hour) from obs_hourly group by source order by source",
        "select count(*), max(issued_slot), max(array_length(pm25, 1)) from cams_fcst",
        "select status, details->'doe'->>'status', details->'aqicn'->>'status' from run_log order by id desc limit 1",
    ]:
        print(conn.execute(sql).fetchall())
EOF
```

Expected:
- `[(68, 63)]` (±1 on the matched count).
- The `doe` row's `min(hour)` is about 7 days ago and `max(hour)` is the current hour; the `aqicn` row has 63 readings.
- `cams_fcst` has 68 rows with up to 120 values each.
- The last run is `ok`.

- [ ] **Step 3: Run again to prove the skips**

```bash
uv --directory pipeline run python -m myhaze.jobs.archive
```

Expected: `doe skipped`, `aqicn skipped`, `cams skipped`, and `stations skipped` (or `ok` if the minute is still below 15); `run: ok`. Then re-run the unit suite (`uv --directory pipeline run pytest -q`): all pass.

No commit (no files changed).

---

### Task 9: Public repo, secrets, scheduled workflow, CI

**Files:**
- Create: `.github/workflows/archive.yml`, `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `python -m myhaze.jobs.archive`; secrets `AQICN_TOKEN` and `SUPABASE_DB_URL`.

- [ ] **Step 1: Write the workflows**

`.github/workflows/archive.yml`:

```yaml
name: archive

on:
  schedule:
    - cron: "5,20,35,50 * * * *"
  workflow_dispatch:
    inputs:
      doe_backfill_days:
        description: "Also fetch DOE's previous N days (DOE keeps about 7)"
        default: "0"

concurrency:
  group: archive
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  archive:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          enable-cache: true
          cache-dependency-glob: pipeline/uv.lock
      - name: Install
        run: uv --directory pipeline sync --frozen
      - name: Archive
        run: uv --directory pipeline run python -m myhaze.jobs.archive --doe-backfill-days "$BACKFILL_DAYS"
        env:
          BACKFILL_DAYS: ${{ inputs.doe_backfill_days || '0' }}
          AQICN_TOKEN: ${{ secrets.AQICN_TOKEN }}
          SUPABASE_DB_URL: ${{ secrets.SUPABASE_DB_URL }}
```

`.github/workflows/ci.yml`:

```yaml
name: ci

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - name: Install
        run: uv --directory pipeline sync --frozen
      - name: Unit tests
        run: uv --directory pipeline run pytest -q
```

Tests stay out of the archive workflow on purpose: a failing test must never stop data from being archived.

- [ ] **Step 2: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add .github
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "ci: 15-minute archive schedule and unit-test workflow

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 3: Create the public repo and push (owner approval required before running)**

Check nothing secret is tracked first:

```bash
cd "/Users/ryanchuah/Claude Code/MYHaze"
git ls-files | grep -E '(^|/)\.env$|data/raw' || echo "clean"
for name in AQICN_TOKEN SUPABASE_DB_URL; do
  value=$(grep "^${name}=" .env | cut -d= -f2-)
  printf '%s in history: ' "$name"; git log -p --all | grep -cF -- "$value" || true
done
```

Expected: `clean`, then `AQICN_TOKEN in history: 0` and `SUPABASE_DB_URL in history: 0`. The values are read from `.env` at run time, so no secret is ever written into this plan.

```bash
gh repo create kiizenitc/myhaze --public \
  --description "48-hour haze Real Feel for Malaysian parents" \
  --source "/Users/ryanchuah/Claude Code/MYHaze" --remote origin --push
```

Expected: the repo URL `https://github.com/kiizenitc/myhaze`, and `main` pushed.

- [ ] **Step 4: Add secrets from `.env` without echoing them**

```bash
cd "/Users/ryanchuah/Claude Code/MYHaze" && for name in AQICN_TOKEN SUPABASE_DB_URL; do
  grep "^${name}=" .env | cut -d= -f2- | gh secret set "$name" -R kiizenitc/myhaze
done && gh secret list -R kiizenitc/myhaze
```

Expected: both names are listed (the values never print).

- [ ] **Step 5: Trigger once and watch it succeed**

```bash
gh workflow run archive.yml -R kiizenitc/myhaze
sleep 5
RUN_ID=$(gh run list -R kiizenitc/myhaze --workflow archive.yml --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch "$RUN_ID" -R kiizenitc/myhaze --exit-status
gh run view "$RUN_ID" -R kiizenitc/myhaze --log | grep -E "^.*(stations|doe|aqicn|cams|run:)" | tail -6
```

Expected: the run succeeds and its log ends with `run: ok`. The steps show `skipped` or `ok`, since Task 8 already stored this hour. The CI workflow from the push also passes: `gh run list -R kiizenitc/myhaze --workflow ci.yml --limit 1` shows `completed success`.

- [ ] **Step 6: Confirm the schedule is firing**

Within about 30 minutes:

```bash
gh run list -R kiizenitc/myhaze --workflow archive.yml --event schedule --limit 3
```

Expected: at least one `schedule` run with `completed success`. Then confirm fresh rows from GitHub's runner (not the laptop):

```bash
uv --directory pipeline run python - <<'EOF'
import psycopg
from myhaze.config import load_settings
with psycopg.connect(load_settings().db_url, prepare_threshold=None) as conn:
    print(conn.execute("select started_at, status from run_log order by id desc limit 4").fetchall())
    print(conn.execute("select source, max(hour), count(*) filter (where hour > now() - interval '2 hours') "
                       "from obs_hourly group by source").fetchall())
EOF
```

Expected: `run_log` entries every 15 minutes, and both sources hold readings for the latest hour.

**Note for Plan 2:** GitHub disables scheduled workflows in a repo with no commits for 60 days. Plan 2's weekly retrain commits its backtest report, which keeps the schedule alive.

---

## Self-review notes

- **Spec coverage for this plan's scope** (§3 item 1, §4 DOE/aqicn/CAMS rows, §7.2 storage, §7.3 hourly schedule, §7.4 failure handling for the archive, §7.5 secrets, §10 compliance): Tasks 1–9.
- **Deferred on purpose:** FIRMS (§4) → Plan 2 Task 1. Conversions (§5), model (§6), publish, verification → Plan 2. Website and Cloudflare (§8, §9) → Plan 3.
- **Owner actions in this plan:** create the Supabase project (Task 6 Step 1) and approve the public repo (Task 9 Step 3).
