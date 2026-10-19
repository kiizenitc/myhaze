"""aqicn (World Air Quality Index) API: Malaysian official stations and their hourly readings.

For DOE stations, `aqi` equals DOE's official API (24-hour average) and `iaqi.pm25`
is this hour's PM2.5 as a US AQI sub-index (verified against DOE on 2026-10-15).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from ..geo import haversine_km  # noqa: F401  (re-exported for callers of aqicn.haversine_km)
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
    time_info = data.get("time")
    iso = time_info.get("iso") if isinstance(time_info, dict) else None
    try:
        hour = datetime.fromisoformat(iso).astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    except (TypeError, ValueError):
        return None
    iaqi = data.get("iaqi") if isinstance(data.get("iaqi"), dict) else {}

    def reading(key: str) -> float | None:
        entry = iaqi.get(key)
        return _num(entry.get("v")) if isinstance(entry, dict) else None

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


NEAR_PAD_DEG = 0.15  # about 17 km either way
NEAR_MAX_LOOKUPS = 12


def fetch_near(client: httpx.Client, token: str, stations: list[Station]) -> list[AqicnStation]:
    """aqicn's map/bounds thins out crowded areas, and differently from call to call, so the country-wide search
    can miss a station (Ipoh's Jalan Tasek never shows in it). A small box around a DOE station lists every
    aqicn station near it."""
    found: list[AqicnStation] = []
    for s in stations[:NEAR_MAX_LOOKUPS]:
        box = (f"{s.lat - NEAR_PAD_DEG:.4f},{s.lon - NEAR_PAD_DEG:.4f},"
               f"{s.lat + NEAR_PAD_DEG:.4f},{s.lon + NEAR_PAD_DEG:.4f}")
        found += parse_bounds(get_json(client, f"{BASE}/map/bounds",
                                       params={"latlng": box, "networks": "official", "token": token},
                                       label="aqicn map/bounds near a station"))
    return found


def fetch_feed(client: httpx.Client, token: str, uid: int, station_id: str) -> Obs | None:
    payload = get_json(client, f"{BASE}/feed/@{uid}/", params={"token": token}, label="aqicn feed")
    return parse_feed(payload, station_id)
