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
