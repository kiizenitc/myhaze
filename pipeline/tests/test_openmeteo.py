from datetime import date, datetime, timezone

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


WEATHER_TWO = [
    {"hourly": {"time": ["2026-10-15T00:00", "2026-10-15T01:00"],
                "precipitation_previous_day1": [0.0, 1.2], "wind_speed_10m_previous_day1": [5.0, 6.0],
                "wind_speed_120m_previous_day1": [12.0, 14.0], "wind_direction_120m_previous_day1": [200, 210],
                "relative_humidity_2m_previous_day1": [80, 85]}},
    {"hourly": {"time": ["2026-10-15T00:00", "2026-10-15T01:00"],
                "precipitation_previous_day1": [None, 0.0], "wind_speed_10m_previous_day1": [3.0, 3.0],
                "wind_speed_120m_previous_day1": [9.0, 9.0], "wind_direction_120m_previous_day1": [90, 95],
                "relative_humidity_2m_previous_day1": [70, 72]}},
]


def test_parse_weather_reads_suffixed_columns_and_marks_missing_ones():
    got = openmeteo.parse_weather(WEATHER_TWO, STATIONS, "_previous_day1")
    assert got[0].times[1] == datetime(2026, 10, 15, 1, tzinfo=timezone.utc)
    assert (got[0].precip, got[0].wind120_from, got[1].precip) == ([0.0, 1.2], [200.0, 210.0], [None, 0.0])
    assert got[0].blh == [None, None]


def test_parse_weather_rejects_a_location_count_mismatch():
    with pytest.raises(FetchError):
        openmeteo.parse_weather(WEATHER_TWO, STATIONS[:1])


def test_fetch_previous_runs_asks_for_the_lead_suffix_and_dates():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=WEATHER_TWO)

    got = openmeteo.fetch_previous_runs(make_client(transport=httpx.MockTransport(handler)), STATIONS,
                                        date(2026, 7, 1), date(2026, 7, 3), lead=1)
    assert len(got) == 2
    assert "wind_direction_120m_previous_day1" in seen[0]["hourly"].split(",")
    assert (seen[0]["start_date"], seen[0]["end_date"]) == ("2026-06-30", "2026-07-03")


def test_fetch_cams_hourly_history_returns_series_per_station():
    def handler(request):
        return httpx.Response(200, json=fixtures.CAMS_TWO_STATIONS)

    got = openmeteo.fetch_cams_hourly_history(make_client(transport=httpx.MockTransport(handler)), STATIONS,
                                              date(2026, 10, 15), date(2026, 10, 15))
    assert got["CA01R"] == {SLOT: 20.1, SLOT.replace(hour=2): 22.5}
