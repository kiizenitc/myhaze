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
