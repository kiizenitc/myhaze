"""Choose the PM2.5 conversion tables from archived data and write calibration.json."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

from ..calibration import calibrate
from ..config import load_settings
from ..convert import CALIBRATION_FILE
from ..store import open_store


def main(argv: list[str] | None = None) -> int:
    settings = load_settings()
    if not settings.db_url:
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 2
    store = open_store(settings.db_url)
    if store is None:
        return 1
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
