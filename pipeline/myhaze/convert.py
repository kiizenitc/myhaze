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
