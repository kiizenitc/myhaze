import copy
from datetime import datetime, timezone

import httpx

from myhaze.config import Settings
from myhaze.http import make_client
from myhaze.jobs import archive
from myhaze.rows import Station
from tests import fixtures
from tests.fakes import FakeStore

NOW = datetime(2026, 10, 15, 0, 5, tzinfo=timezone.utc)  # 08:05 in Malaysia
HOUR = datetime(2026, 10, 15, 0, tzinfo=timezone.utc)
SETTINGS = Settings(aqicn_token="tok123", db_url="postgresql://unused")
KANGAR = Station("CA01R", "Kangar", "Perlis", 6.429928, 100.210937)
IPOH = Station("CA10A", "Jalan Tasek", "Perak", 4.6293, 101.1157)

HEALTHY = {
    "mapcaqm": fixtures.DOE_STATIONS,
    "statelist": fixtures.DOE_STATELIST,
    "apitablehourly": fixtures.DOE_HOURLY_NOW,
    "/map/bounds": fixtures.AQICN_BOUNDS,
    "/feed/@3001/": fixtures.AQICN_FEED_KANGAR,
    "/v1/air-quality": fixtures.CAMS_TWO_STATIONS,
}


def routed_client(routes, calls):
    """routes maps a URL-path suffix to a JSON payload, or to an int HTTP status."""
    def handler(request):
        calls.append(request.url.path)
        for suffix, reply in routes.items():
            if request.url.path.endswith(suffix):
                if isinstance(reply, int):
                    return httpx.Response(reply)
                return httpx.Response(200, json=reply)
        return httpx.Response(404)
    return make_client(transport=httpx.MockTransport(handler))


def test_first_run_archives_doe_aqicn_and_cams():
    store = FakeStore()
    result = archive.run(NOW, SETTINGS, routed_client(HEALTHY, []), store)

    assert result.status == "ok", result.details
    assert store.aqicn_uids() == {"CA01R": 3001}
    assert {k for k in store.obs if k[2] == "doe"} == {("CA01R", HOUR, "doe"), ("MCAQM001", HOUR, "doe")}
    assert result.details["doe"]["unknown_station"] == 1
    assert store.obs[("CA01R", HOUR, "aqicn")].pm25_aqi == 130
    assert len(store.cams) == 2
    assert store.runs[-1][:2] == ("archive", "ok")


def test_second_run_in_the_same_hour_makes_no_requests():
    store, calls = FakeStore(), []
    client = routed_client(HEALTHY, calls)
    archive.run(NOW, SETTINGS, client, store)
    first_run_calls = len(calls)

    result = archive.run(NOW.replace(minute=20), SETTINGS, client, store)

    assert len(calls) == first_run_calls
    assert {d["status"] for d in result.details.values()} == {"skipped"}
    assert result.status == "ok"


def test_one_failing_aqicn_station_does_not_block_the_others():
    store = FakeStore(stations=[KANGAR, IPOH], aqicn={"CA01R": 3001, "CA10A": 4004})
    routes = dict(HEALTHY, **{"/feed/@4004/": 500})

    result = archive.run(NOW.replace(minute=30), SETTINGS, routed_client(routes, []), store)

    assert result.details["aqicn"]["status"] == "partial"
    assert ("CA01R", HOUR, "aqicn") in store.obs
    assert "tok123" not in str(result.details)
    assert result.status == "partial"


def test_run_fails_when_aqicn_fails_even_if_doe_is_fine():
    store = FakeStore(stations=[KANGAR], aqicn={"CA01R": 3001})
    routes = dict(HEALTHY, **{"/feed/@3001/": 503, "/v1/air-quality": fixtures.CAMS_TWO_STATIONS[0]})

    result = archive.run(NOW.replace(minute=30), SETTINGS, routed_client(routes, []), store)

    assert result.details["doe"]["status"] == "ok"
    assert result.details["aqicn"]["status"] == "failed"
    assert result.details["cams"]["status"] == "ok"
    assert result.status == "failed"
    assert store.runs[-1][1] == "failed"


def test_doe_failing_alone_leaves_the_run_partial():
    store = FakeStore(stations=[KANGAR], aqicn={"CA01R": 3001})
    routes = dict(HEALTHY, **{"statelist": 503, "/v1/air-quality": fixtures.CAMS_TWO_STATIONS[0]})

    result = archive.run(NOW.replace(minute=30), SETTINGS, routed_client(routes, []), store)

    assert (result.details["doe"]["status"], result.status) == ("failed", "partial")


def test_doe_backfill_requests_one_window_per_day():
    store, stamps = FakeStore(stations=[KANGAR]), []

    def handler(request):
        if request.url.path.endswith("statelist"):
            return httpx.Response(200, json=[{"STATE_ID": 9}])
        stamps.append(request.url.params["datetime"])
        return httpx.Response(200, json=fixtures.DOE_HOURLY)

    detail = archive.archive_doe(make_client(transport=httpx.MockTransport(handler)), store, NOW, backfill_days=2)

    assert stamps == ["2026-10-15T08:00:00", "2026-10-14T08:00:00", "2026-10-13T08:00:00"]
    assert (detail["status"], detail["written"]) == ("ok", 2)


def test_a_sharply_shrunken_aqicn_mapping_is_ignored():
    many = [Station(f"CA{i:02d}X", f"Station {i}", "Test", 1.0 + i, 101.0) for i in range(10)]
    store = FakeStore(stations=many, aqicn={s.station_id: 9000 + i for i, s in enumerate(many)})

    detail = archive.sync_stations(routed_client(HEALTHY, []), store, SETTINGS, NOW)

    assert "aqicn_mapping_rejected" in detail
    assert len(store.aqicn_uids()) == 10


def test_missing_token_skips_aqicn_without_failing():
    store = FakeStore(stations=[KANGAR])
    detail = archive.archive_aqicn(routed_client(HEALTHY, []), store, Settings(None, "x"), NOW)
    assert detail == {"status": "skipped", "reason": "AQICN_TOKEN not set"}


class ExplodingDoeStore(FakeStore):
    def count_obs_at(self, source, hour):
        raise RuntimeError("database said: password=SECRETPW")


class BrokenLogStore(FakeStore):
    def log_run(self, *args):
        raise RuntimeError("connection lost")


def test_an_unexpected_error_in_one_step_does_not_stop_the_others():
    store = ExplodingDoeStore(stations=[KANGAR], aqicn={"CA01R": 3001})
    routes = dict(HEALTHY, **{"/v1/air-quality": fixtures.CAMS_TWO_STATIONS[0]})

    result = archive.run(NOW.replace(minute=30), SETTINGS, routed_client(routes, []), store)

    assert result.details["doe"] == {"status": "failed", "errors": ["RuntimeError"]}
    assert ("CA01R", HOUR, "aqicn") in store.obs
    assert result.details["cams"]["status"] == "ok"
    assert store.runs and "SECRETPW" not in str(store.runs[-1])


def test_aqicn_is_archived_before_doe_is_touched():
    calls = []
    archive.run(NOW, SETTINGS, routed_client(HEALTHY, calls), FakeStore())
    first_feed = calls.index("/feed/@3001/")
    first_doe = next(i for i, path in enumerate(calls) if path.endswith("statelist"))
    assert first_feed < first_doe


def test_a_failed_run_log_write_marks_the_run_failed():
    result = archive.run(NOW, SETTINGS, routed_client(HEALTHY, []), BrokenLogStore())
    assert result.status == "failed"
    assert result.details["run_log"] == {"status": "failed", "errors": ["RuntimeError"]}


class FakeClock:
    """Each reading advances time by `step` seconds."""
    def __init__(self, step):
        self.now, self.step = 0.0, step

    def __call__(self):
        self.now += self.step
        return self.now


def test_doe_stops_when_its_time_budget_runs_out():
    store, stamps = FakeStore(stations=[KANGAR]), []

    def handler(request):
        if request.url.path.endswith("statelist"):
            return httpx.Response(200, json=[{"STATE_ID": s} for s in range(1, 17)])
        stamps.append(request.url.params["stateid"])
        return httpx.Response(200, json=fixtures.DOE_HOURLY)

    detail = archive.archive_doe(make_client(transport=httpx.MockTransport(handler)), store, NOW,
                                 budget_s=150, clock=FakeClock(60))

    assert stamps == ["1", "2"]
    assert detail["status"] == "partial"
    assert any("time budget" in e for e in detail["errors"])


def test_aqicn_stops_when_its_time_budget_runs_out_but_keeps_what_it_got():
    many = [Station(f"CA{i:02d}X", f"Station {i}", "Test", 1.0 + i, 101.0) for i in range(5)]
    store = FakeStore(stations=many, aqicn={s.station_id: 3001 for s in many})

    detail = archive.archive_aqicn(routed_client({"/feed/@3001/": fixtures.AQICN_FEED_KANGAR}, []), store,
                                   SETTINGS, NOW, budget_s=150, clock=FakeClock(60))

    assert detail["written"] == 2
    assert detail["status"] == "partial"
    assert any("time budget" in e for e in detail["errors"])


def test_aqicn_returning_no_readings_fails_the_run():
    store = FakeStore(stations=[KANGAR], aqicn={"CA01R": 4004})
    routes = dict(HEALTHY, **{"/feed/@4004/": fixtures.AQICN_FEED_OFFLINE,
                              "/v1/air-quality": fixtures.CAMS_TWO_STATIONS[0]})

    result = archive.run(NOW.replace(minute=30), SETTINGS, routed_client(routes, []), store)

    assert result.details["aqicn"]["status"] == "failed"
    assert result.status == "failed"


def test_a_feed_stuck_on_an_old_hour_is_a_failure():
    stuck = copy.deepcopy(fixtures.AQICN_FEED_KANGAR)
    stuck["data"]["time"]["iso"] = "2026-10-15T05:00:00+08:00"  # three hours before NOW
    store = FakeStore(stations=[KANGAR], aqicn={"CA01R": 3001})

    detail = archive.archive_aqicn(routed_client({"/feed/@3001/": stuck}, []), store, SETTINGS, NOW)

    assert (detail["written"], detail["status"]) == (1, "failed")


def test_aqicn_without_any_matched_station_is_a_failure():
    detail = archive.archive_aqicn(routed_client(HEALTHY, []), FakeStore(stations=[KANGAR]), SETTINGS, NOW)
    assert detail["status"] == "failed"


def test_doe_readings_only_for_unknown_stations_is_a_failure():
    detail = archive.archive_doe(routed_client(HEALTHY, []), FakeStore(stations=[IPOH]), NOW)
    assert (detail["written"], detail["status"]) == (0, "failed")


def test_main_reports_a_connection_failure_without_echoing_it(monkeypatch, capsys):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://user:SECRETPW@db.example/postgres")

    def refuse(cls, db_url):
        raise RuntimeError(f"invalid connection option in {db_url}")

    from myhaze.store import Store

    monkeypatch.setattr(Store, "connect", classmethod(refuse))

    assert archive.main([]) == 1
    output = capsys.readouterr()
    assert "SECRETPW" not in output.out + output.err
    assert "RuntimeError" in output.err


def test_fires_step_stores_cells_once_per_hour():
    from tests.test_firms import AVAILABILITY, CSV

    store = FakeStore(stations=[KANGAR], aqicn={"CA01R": 3001})
    routes = dict(HEALTHY, **{"/data_availability/csv/FK/ALL": AVAILABILITY,
                              "/v1/air-quality": fixtures.CAMS_TWO_STATIONS[0]})

    def handler(request):
        for suffix, reply in routes.items():
            if request.url.path.endswith(suffix):
                return httpx.Response(200, json=reply) if not isinstance(reply, str) else httpx.Response(200, text=reply)
        if "/api/area/csv/FK/" in request.url.path:
            return httpx.Response(200, text=CSV)
        return httpx.Response(404)

    settings = Settings("tok123", "postgresql://unused", "FK")
    client = make_client(transport=httpx.MockTransport(handler))
    result = archive.run(NOW, settings, client, store)
    assert result.details["fires"]["status"] == "ok"
    assert len(store.fire_cells_store) == 2

    later = archive.archive_fires(client, store, settings, NOW.replace(minute=20))
    assert later == {"status": "skipped", "reason": "fetched at the start of the hour"}


def test_fires_step_is_skipped_without_a_key():
    detail = archive.archive_fires(routed_client(HEALTHY, []), FakeStore(), SETTINGS, NOW)
    assert detail == {"status": "skipped", "reason": "FIRMS_MAP_KEY not set"}


def test_stations_the_country_wide_aqicn_search_leaves_out_get_a_close_look():
    # aqicn's map/bounds thins out crowded areas (Ipoh's Jalan Tasek only shows in a small box around it).
    from myhaze.sources import aqicn

    near = {"status": "ok", "data": [{"lat": 2.98, "lon": 101.47, "uid": 7007, "aqi": "160",
                                      "station": {"name": "Johan Setia, Selangor, Malaysia",
                                                  "time": "2026-10-15T08:00:00+08:00"}}]}
    boxes = []

    def handler(request):
        if request.url.path.endswith("mapcaqm"):
            return httpx.Response(200, json=fixtures.DOE_STATIONS)
        if request.url.path.endswith("/map/bounds"):
            boxes.append(request.url.params["latlng"])
            country = request.url.params["latlng"] == aqicn.MALAYSIA_BOUNDS
            return httpx.Response(200, json=fixtures.AQICN_BOUNDS if country else near)
        return httpx.Response(404)

    store = FakeStore()
    archive.sync_stations(make_client(transport=httpx.MockTransport(handler)), store, SETTINGS, NOW)
    assert store.aqicn_uids() == {"CA01R": 3001, "MCAQM001": 7007}
    assert len(boxes) == 2  # one country-wide search, one close look for the station it left out
