"""Supabase Postgres access for the archive (direct connection through the session pooler)."""
from __future__ import annotations

from datetime import date, datetime

import psycopg
from psycopg.types.json import Jsonb

from .rows import CamsForecast, FireCell, HourlyWeather, Obs, Station
from .weather import WeatherDay

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
                # Reset only the stations being synced, so a partial call never unlinks the rest.
                cur.execute("update stations set aqicn_uid = null, aqicn_km = null where station_id = any(%s)",
                            ([s.station_id for s in stations],))
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
