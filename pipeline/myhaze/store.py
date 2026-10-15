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
