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


def test_run_fails_only_when_doe_and_aqicn_are_both_down():
    store = FakeStore(stations=[KANGAR], aqicn={"CA01R": 3001})
    routes = {"statelist": 503, "/feed/@3001/": 503, "/v1/air-quality": fixtures.CAMS_TWO_STATIONS[0]}

    result = archive.run(NOW.replace(minute=30), SETTINGS, routed_client(routes, []), store)

    assert result.details["doe"]["status"] == "failed"
    assert result.details["aqicn"]["status"] == "failed"
    assert result.details["cams"]["status"] == "ok"
    assert result.status == "failed"
    assert store.runs[-1][1] == "failed"


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
