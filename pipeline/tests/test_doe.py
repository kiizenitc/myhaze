from datetime import datetime, timezone

import httpx
import pytest

from myhaze.http import FetchError, make_client
from myhaze.sources import doe
from tests import fixtures


def client_returning(payload, seen=None):
    def handler(request):
        if seen is not None:
            seen.update(dict(request.url.params))
        return httpx.Response(200, json=payload)
    return make_client(transport=httpx.MockTransport(handler))


def test_parse_stations_keeps_valid_rows_and_tidies_names():
    stations = doe.parse_stations(fixtures.DOE_STATIONS)
    assert [(s.station_id, s.name, s.state) for s in stations] == [
        ("CA01R", "Kangar", "Perlis"),
        ("MCAQM001", "Johan Setia", "Selangor"),
    ]
    assert (stations[0].lat, stations[0].lon) == (6.429928, 100.210937)


def test_parse_hourly_converts_myt_to_utc_and_drops_missing_values():
    rows = doe.parse_hourly(fixtures.DOE_HOURLY)
    assert [(r.station_id, r.hour, r.api) for r in rows] == [
        ("CA01R", datetime(2026, 10, 14, 16, tzinfo=timezone.utc), 57),
        ("CA01R", datetime(2026, 10, 14, 19, tzinfo=timezone.utc), 62),
    ]
    assert all(r.source == "doe" and r.param_symbol == "**" for r in rows)


def test_fetch_hourly_asks_for_the_malaysia_hour():
    seen = {}
    at = datetime(2026, 10, 15, 0, 30, tzinfo=timezone.utc)  # 08:30 in Malaysia
    doe.fetch_hourly(client_returning(fixtures.DOE_HOURLY, seen), 14, at)
    assert seen == {"stateid": "14", "datetime": "2026-10-15T08:00:00"}


def test_fetch_state_ids_reads_the_state_list():
    assert doe.fetch_state_ids(client_returning(fixtures.DOE_STATELIST)) == [9, 10]


def test_fetch_state_ids_rejects_an_unexpected_shape():
    with pytest.raises(FetchError):
        doe.fetch_state_ids(client_returning({"oops": 1}))
