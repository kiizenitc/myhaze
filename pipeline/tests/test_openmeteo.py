from datetime import datetime, timezone

import httpx
import pytest

from myhaze.config import MYT
from myhaze.http import FetchError, make_client
from myhaze.rows import Station
from myhaze.sources import openmeteo
from tests import fixtures

STATIONS = [Station("CA01R", "Kangar", "Perlis", 6.429928, 100.210937),
            Station("MCAQM001", "Johan Setia", "Selangor", 2.98, 101.47)]
SLOT = datetime(2026, 10, 15, 0, tzinfo=timezone.utc)


def test_six_hour_slot_floors_in_utc():
    assert openmeteo.six_hour_slot(datetime(2026, 10, 15, 13, 40, tzinfo=timezone.utc)) == \
        datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
    assert openmeteo.six_hour_slot(datetime(2026, 10, 15, 5, 0, tzinfo=MYT)) == \
        datetime(2026, 10, 14, 18, tzinfo=timezone.utc)


def test_parse_cams_maps_locations_to_stations_in_order():
    got = openmeteo.parse_cams(fixtures.CAMS_TWO_STATIONS, STATIONS, SLOT)
    assert [(c.station_id, c.first_valid, c.pm25) for c in got] == [
        ("CA01R", SLOT, [20.1, None, 22.5]),
        ("MCAQM001", SLOT, [61.0, 64.2, 70.9]),
    ]
    assert all(c.issued_slot == SLOT for c in got)


def test_parse_cams_accepts_a_single_object_for_one_station():
    got = openmeteo.parse_cams(fixtures.CAMS_TWO_STATIONS[0], STATIONS[:1], SLOT)
    assert [c.station_id for c in got] == ["CA01R"]


def test_parse_cams_rejects_a_location_count_mismatch():
    with pytest.raises(FetchError):
        openmeteo.parse_cams(fixtures.CAMS_TWO_STATIONS, STATIONS[:1], SLOT)


def test_fetch_cams_sends_coordinates_and_asks_for_gmt():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=fixtures.CAMS_TWO_STATIONS)

    got = openmeteo.fetch_cams(make_client(transport=httpx.MockTransport(handler)), STATIONS, SLOT)
    assert len(got) == 2 and len(seen) == 1
    assert seen[0]["latitude"] == "6.4299,2.9800"
    assert seen[0]["longitude"] == "100.2109,101.4700"
    assert (seen[0]["hourly"], seen[0]["timezone"], seen[0]["forecast_days"]) == ("pm2_5", "GMT", "5")


def test_parse_cams_turns_unreadable_values_into_gaps():
    payload = {"hourly": {"time": ["2026-10-15T00:00", "2026-10-15T01:00"], "pm2_5": ["x", 5]}}
    assert openmeteo.parse_cams(payload, STATIONS[:1], SLOT)[0].pm25 == [None, 5.0]


def test_parse_cams_skips_locations_with_unreadable_shapes():
    payload = [{"hourly": {"time": [123], "pm2_5": [1.0]}}, "junk"]
    assert openmeteo.parse_cams(payload, STATIONS, SLOT) == []
