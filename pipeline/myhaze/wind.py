"""The map's flowing-wind layer: Open-Meteo's wind about 120 m up (the wind that carries smoke) on a 1° grid
over Sumatra, the Peninsula and Borneo."""
from __future__ import annotations

import math
from datetime import timezone

from .rows import HourlyWeather, Station

LON0, LAT0, DLON, DLAT, NX, NY = 95.0, -7.0, 1.0, 1.0, 27, 17  # 95–121°E, 7°S–9°N
FRAME_STEP_H = 3


def grid_points() -> list[Station]:
    """Row by row from the south-west corner: index = row * NX + column."""
    return [Station(f"WG{j:02d}{i:02d}", "wind grid", "", LAT0 + j * DLAT, LON0 + i * DLON)
            for j in range(NY) for i in range(NX)]


def to_uv(kmh: float | None, from_deg: float | None) -> tuple[float | None, float | None]:
    """Wind blowing FROM `from_deg` at `kmh`, as eastward and northward components in m/s."""
    if kmh is None or from_deg is None:
        return None, None
    speed, angle = kmh / 3.6, math.radians(from_deg)
    return round(-speed * math.sin(angle), 1) + 0.0, round(-speed * math.cos(angle), 1) + 0.0


def hourly_field(weather: list[HourlyWeather]) -> dict:
    """{"times", "u", "v"}: for every hour, one value per grid point in grid order (null where missing)."""
    columns = {w.station_id: (w, {t: k for k, t in enumerate(w.times)}) for w in weather}
    times = sorted({t for w in weather for t in w.times})
    u, v = [], []
    for t in times:
        row_u, row_v = [], []
        for point in grid_points():
            w, index = columns.get(point.station_id, (None, {}))
            k = index.get(t)
            a, b = to_uv(w.wind120[k], w.wind120_from[k]) if w is not None and k is not None else (None, None)
            row_u.append(a)
            row_v.append(b)
        u.append(row_u)
        v.append(row_v)
    return {"times": [t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") for t in times], "u": u, "v": v}
