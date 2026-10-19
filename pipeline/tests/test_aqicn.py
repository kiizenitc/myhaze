from datetime import datetime, timezone

import httpx
import pytest

from myhaze.http import FetchError, make_client
from myhaze.rows import Station
from myhaze.sources import aqicn
from tests import fixtures

KANGAR = Station("CA01R", "Kangar", "Perlis", 6.429928, 100.210937)
IPOH_DOE = Station("CA10A", "Jalan Tasek", "Perak", 4.6293, 101.1157)  # about 6 km from aqicn's Ipoh point
KAPIT = Station("CA40Q", "Kapit", "Sarawak", 2.0154, 112.9365)


def test_parse_bounds_keeps_only_malaysian_stations():
    got = aqicn.parse_bounds(fixtures.AQICN_BOUNDS)
    assert [(s.uid, s.name) for s in got] == [(3001, "Kangar, Perlis, Malaysia"), (4004, "Ipoh, Perak, Malaysia")]


def test_match_stations_pairs_nearest_within_the_limit():
    got = aqicn.match_stations([KANGAR, IPOH_DOE, KAPIT], aqicn.parse_bounds(fixtures.AQICN_BOUNDS))
    assert set(got) == {"CA01R", "CA10A"}
    assert got["CA01R"] == (3001, 0.0)
    assert got["CA10A"][0] == 4004 and 4 < got["CA10A"][1] < 10


def test_match_stations_gives_each_uid_to_one_station_only():
    twin = Station("CA01X", "Kangar twin", "Perlis", 6.45, 100.22)  # about 2.5 km from Kangar
    got = aqicn.match_stations([twin, KANGAR], aqicn.parse_bounds(fixtures.AQICN_BOUNDS))
    assert got == {"CA01R": (3001, 0.0)}


def test_parse_feed_reads_official_api_and_hourly_pm25():
    obs = aqicn.parse_feed(fixtures.AQICN_FEED_KANGAR, "CA01R")
    assert obs.hour == datetime(2026, 10, 15, 0, tzinfo=timezone.utc)
    assert (obs.source, obs.api, obs.pm25_aqi, obs.pm10_aqi) == ("aqicn", 56, 130, 52)
    assert (obs.temp_c, obs.rh, obs.wind, obs.pressure, obs.co_aqi) == (25, 94, 1, 1011, 0.1)


def test_parse_feed_returns_none_when_the_station_is_offline():
    assert aqicn.parse_feed(fixtures.AQICN_FEED_OFFLINE, "CA10A") is None


def test_parse_feed_raises_on_error_status():
    with pytest.raises(FetchError) as info:
        aqicn.parse_feed(fixtures.AQICN_FEED_ERROR, "CA10A")
    assert "status 'error'" in str(info.value)


def test_fetch_feed_sends_the_token_as_a_query_parameter():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["token"] = request.url.params["token"]
        return httpx.Response(200, json=fixtures.AQICN_FEED_KANGAR)

    obs = aqicn.fetch_feed(make_client(transport=httpx.MockTransport(handler)), "tok123", 3001, "CA01R")
    assert seen == {"path": "/feed/@3001/", "token": "tok123"}
    assert obs.station_id == "CA01R"


def test_parse_feed_returns_none_when_time_is_not_an_object():
    payload = {"status": "ok", "data": {"aqi": 50, "time": "2026-10-15 08:00:00", "iaqi": {"pm25": {"v": 60}}}}
    assert aqicn.parse_feed(payload, "CA01R") is None


def test_parse_feed_ignores_malformed_readings():
    payload = {"status": "ok", "data": {"aqi": 50, "time": {"iso": "2026-10-15T08:00:00+08:00"},
                                        "iaqi": {"pm25": 60, "t": {"v": "x"}}}}
    obs = aqicn.parse_feed(payload, "CA01R")
    assert (obs.api, obs.pm25_aqi, obs.temp_c) == (50, None, None)


def test_fetch_near_looks_in_a_small_official_box_around_each_station():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=fixtures.AQICN_BOUNDS)

    got = aqicn.fetch_near(make_client(transport=httpx.MockTransport(handler)), "tok", [KANGAR])
    assert seen[0]["latlng"] == "6.2799,100.0609,6.5799,100.3609" and seen[0]["networks"] == "official"
    assert 3001 in {c.uid for c in got}
