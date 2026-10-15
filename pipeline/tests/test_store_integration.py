from datetime import datetime, timedelta, timezone

import pytest

from myhaze.config import load_settings
from myhaze.migrate import apply_migrations
from myhaze.rows import CamsForecast, Obs, Station
from myhaze.store import Store

pytestmark = pytest.mark.integration
TEST_ID = "ZZTEST"
OLD_HOUR = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def store():
    settings = load_settings()
    if not settings.db_url:
        pytest.skip("SUPABASE_DB_URL is not set")
    s = Store.connect(settings.db_url)
    apply_migrations(s.conn)
    s.upsert_stations([Station(TEST_ID, "Test station", "Nowhere", 0.0, 0.0)])
    yield s
    for table in ("obs_hourly", "cams_fcst", "stations"):
        s.conn.execute(f"delete from {table} where station_id = %s", (TEST_ID,))
    s.conn.execute("delete from run_log where job = 'test'")
    s.close()


def test_upsert_obs_is_idempotent_and_skips_unknown_stations(store):
    assert store.upsert_obs([Obs(TEST_ID, OLD_HOUR, "doe", api=99), Obs("NOPE1", OLD_HOUR, "doe", api=1)]) == (1, 1)
    assert store.upsert_obs([Obs(TEST_ID, OLD_HOUR, "doe", api=101)]) == (1, 0)
    count, api = store.conn.execute(
        "select count(*), max(api) from obs_hourly where station_id = %s", (TEST_ID,)).fetchone()
    assert (count, api) == (1, 101)
    assert store.count_obs_at("doe", OLD_HOUR) >= 1


def test_latest_hours_reports_recent_hours_only(store):
    recent = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    store.upsert_obs([Obs(TEST_ID, OLD_HOUR, "aqicn", api=5), Obs(TEST_ID, recent, "aqicn", api=6, pm25_aqi=130)])
    assert store.latest_hours("aqicn")[TEST_ID] == recent


def test_stations_and_aqicn_mapping_roundtrip(store):
    store.upsert_stations([Station(TEST_ID, "Renamed", "Nowhere", 0.0, 0.0)], {TEST_ID: (999999, 1.25)})
    assert store.aqicn_uids()[TEST_ID] == 999999
    assert any(s.station_id == TEST_ID and s.name == "Renamed" for s in store.stations())
    store.upsert_stations([Station(TEST_ID, "Renamed", "Nowhere", 0.0, 0.0)])  # None keeps the mapping
    assert store.aqicn_uids()[TEST_ID] == 999999


def test_cams_roundtrip_keeps_missing_values(store):
    slot = datetime(2026, 1, 1, 6, tzinfo=timezone.utc)
    assert store.upsert_cams([CamsForecast(TEST_ID, slot, slot, [1.5, None, 3.0])]) == 1
    assert store.cams_slot_done(slot)
    (values,) = store.conn.execute(
        "select pm25 from cams_fcst where station_id = %s and issued_slot = %s", (TEST_ID, slot)).fetchone()
    assert values == [1.5, None, 3.0]


def test_run_log_accepts_json_details(store):
    store.log_run("test", OLD_HOUR, OLD_HOUR, "ok", {"doe": {"status": "ok", "written": 3}})
    (details,) = store.conn.execute("select details from run_log where job = 'test'").fetchone()
    assert details == {"doe": {"status": "ok", "written": 3}}


def test_every_table_has_row_level_security(store):
    rows = store.conn.execute(
        "select relname, relrowsecurity from pg_class "
        "where relnamespace = 'public'::regnamespace and relkind = 'r'").fetchall()
    assert rows and all(enabled for _, enabled in rows), rows


def test_mapping_update_leaves_other_stations_alone(store):
    other = "ZZTES2"
    store.upsert_stations([Station(other, "Other test station", "Nowhere", 0.0, 0.0)], {other: (888888, 0.5)})
    try:
        store.upsert_stations([Station(TEST_ID, "Test station", "Nowhere", 0.0, 0.0)], {TEST_ID: (999999, 1.25)})
        assert store.aqicn_uids().get(other) == 888888
    finally:
        store.conn.execute("delete from stations where station_id = %s", (other,))


def test_fire_cells_roundtrip_and_upsert(store):
    from datetime import date

    from myhaze.rows import FireCell

    day = date(1999, 1, 1)
    try:
        assert store.upsert_fire_cells([FireCell(day, -2.25, 113.75, 20.0, 2)]) == 1
        store.upsert_fire_cells([FireCell(day, -2.25, 113.75, 25.5, 3)])
        assert store.fire_cells(day, day) == [FireCell(day, -2.25, 113.75, 25.5, 3)]
    finally:
        store.conn.execute("delete from fire_grid_daily where day = %s", (day,))


def test_hourly_series_filters_by_source_and_symbol(store):
    recent = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    store.upsert_obs([Obs(TEST_ID, recent, "doe", api=120, param_symbol="**"),
                      Obs(TEST_ID, recent - timedelta(hours=1), "doe", api=40, param_symbol="c"),
                      Obs(TEST_ID, recent, "aqicn", api=120, pm25_aqi=150)])
    since = recent - timedelta(hours=5)
    assert store.hourly_series("doe", "api", since, param_symbol="**")[TEST_ID] == {recent: 120.0}
    assert store.hourly_series("aqicn", "pm25_aqi", since)[TEST_ID] == {recent: 150.0}
