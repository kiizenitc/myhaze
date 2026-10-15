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
