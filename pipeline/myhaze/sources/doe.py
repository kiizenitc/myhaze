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
