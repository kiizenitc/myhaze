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
    for table in ("obs_hourly", "cams_fcst", "daily_pm25", "cams_daily", "stations"):
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


def test_daily_pm25_prefers_archive_over_csv(store):
    from datetime import date

    day = date(1999, 1, 2)
    store.upsert_daily_pm25([(TEST_ID, day, 40.0, "aqicn_csv"), (TEST_ID, day, 42.5, "archive"),
                             (TEST_ID, date(1999, 1, 3), 50.0, "aqicn_csv")])
    try:
        got = store.daily_pm25(day, date(1999, 1, 3))
        assert got[(TEST_ID, day)] == 42.5 and got[(TEST_ID, date(1999, 1, 3))] == 50.0
    finally:
        store.conn.execute("delete from daily_pm25 where station_id = %s", (TEST_ID,))


def test_weather_tables_roundtrip(store):
    from datetime import date

    from myhaze.rows import HourlyWeather
    from myhaze.weather import WeatherDay

    day = date(1999, 1, 4)
    wd = WeatherDay(2.5, 3, 4.0, 12.0, 225.0, 80.0)
    hour = datetime(1999, 1, 4, tzinfo=timezone.utc)
    hw = HourlyWeather("ZZTEST", [hour, hour + timedelta(hours=1)], [0.0, None], [300.0, 250.0], [1.0, 2.0],
                       [5.0, 6.0], [200.0, 210.0], [70.0, 75.0])
    try:
        store.upsert_weather_daily([("ZZTEST", day, 1, wd)])
        assert store.weather_daily(day, day) == {("ZZTEST", day, 1): wd}
        store.save_weather_latest([hw], hour)
        issued, latest = store.weather_latest()
        assert issued == hour and latest["ZZTEST"] == hw
    finally:
        store.conn.execute("delete from weather_daily where station_id = 'ZZTEST'")
        store.conn.execute("delete from weather_latest where station_id = 'ZZTEST'")


def test_cams_daily_and_latest_cams(store):
    from datetime import date

    store.upsert_cams_daily([(TEST_ID, date(1999, 1, 5), 33.3), ("NOPE1", date(1999, 1, 5), 1.0)])
    slot = datetime(1999, 1, 5, 6, tzinfo=timezone.utc)
    store.upsert_cams([CamsForecast(TEST_ID, slot, slot, [10.0, 11.0])])
    try:
        assert store.cams_daily(date(1999, 1, 5), date(1999, 1, 5)) == {(TEST_ID, date(1999, 1, 5)): pytest.approx(33.3)}
        assert store.latest_cams()[TEST_ID].pm25 == [10.0, 11.0]
        assert store.max_day("cams_daily") is not None
    finally:
        store.conn.execute("delete from cams_daily where station_id = %s", (TEST_ID,))


def test_model_versions_roundtrip(store):
    try:
        store.save_model_version("ZZ0001", {1: "model", 2: "persistence"}, {"note": "test"},
                                 {1: {0.1: "low-text", 0.5: "mid-text", 0.9: "high-text"}, 2: {}})
        methods, report, boosters = store.load_model("ZZ0001")
        assert methods == {1: "model", 2: "persistence"} and report == {"note": "test"}
        assert boosters == {1: {0.1: "low-text", 0.5: "mid-text", 0.9: "high-text"}}
        assert store.load_model("ZZ-missing") is None
    finally:
        store.conn.execute("delete from model_versions where version like 'ZZ%'")


def test_forecast_runs_latest_obs_and_doe_daily_max(store):
    from datetime import date

    hour = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    store.upsert_obs([Obs(TEST_ID, hour, "doe", api=161, param_symbol="**")])
    try:
        assert store.latest_obs("doe", "api", hour - timedelta(hours=2))[TEST_ID] == (hour, 161.0)
        local_day = (hour + timedelta(hours=8)).date()
        assert store.doe_daily_max(local_day - timedelta(days=1))[(TEST_ID, local_day)] == 161.0
        store.save_forecast_runs(hour, [(TEST_ID, "model", hour, [50.0, 51.0], [120.0, 121.0])])
        assert (hour, TEST_ID, hour, [50.0, 51.0]) in store.forecast_runs(hour - timedelta(hours=1))
        store.upsert_verification([(date(1999, 1, 6), "1-24h", 10, 9, 4, 4)])
        summary = store.verification_summary(days=100000)
        assert summary["1-24h"]["hours"] >= 10
    finally:
        store.conn.execute("delete from forecast_runs where station_id = %s", (TEST_ID,))
        store.conn.execute("delete from verification_daily where day = %s", (date(1999, 1, 6),))
