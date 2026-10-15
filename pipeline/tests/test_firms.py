from datetime import date

import httpx
import pytest

from myhaze.http import FetchError, make_client
from myhaze.sources import firms

CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
    "-2.21,113.92,330.1,0.4,0.4,2026-10-14,0542,N,VIIRS,n,2.0NRT,290.1,12.5,D\n"
    "-2.24,113.99,331.0,0.4,0.4,2026-10-14,0542,N,VIIRS,h,2.0NRT,291.0,7.5,D\n"
    "-2.21,113.92,300.0,0.4,0.4,2026-10-14,0542,N,VIIRS,l,2.0NRT,280.0,99.0,D\n"
    "1.67,101.45,333.3,0.4,0.4,2026-10-14,1812,N,VIIRS,n,2.0NRT,292.2,3.0,N\n"
    "oops,101.45,333.3,0.4,0.4,2026-10-14,1812,N,VIIRS,n,2.0NRT,292.2,3.0,N\n"
)
AVAILABILITY = (
    "data_id,min_date,max_date\n"
    "VIIRS_SNPP_NRT,2026-08-15,2026-10-15\n"
    "VIIRS_SNPP_SP,2012-01-20,2026-08-31\n"
    "VIIRS_NOAA20_NRT,2026-08-15,2026-10-15\n"
    "VIIRS_NOAA20_SP,2018-04-01,2026-08-31\n"
)


def test_parse_area_csv_skips_low_confidence_and_bad_rows():
    rows = firms.parse_area_csv(CSV)
    assert rows == [(date(2026, 10, 14), -2.21, 113.92, 12.5), (date(2026, 10, 14), -2.24, 113.99, 7.5),
                    (date(2026, 10, 14), 1.67, 101.45, 3.0)]


def test_parse_area_csv_rejects_non_csv_replies():
    with pytest.raises(FetchError):
        firms.parse_area_csv("Invalid MAP_KEY.")


def test_to_cells_sums_frp_per_quarter_degree_cell():
    cells = firms.to_cells(firms.parse_area_csv(CSV))
    assert [(c.day, c.lat_bin, c.lon_bin, c.frp_sum, c.detections) for c in cells] == [
        (date(2026, 10, 14), -2.25, 113.75, 20.0, 2),
        (date(2026, 10, 14), 1.5, 101.25, 3.0, 1),
    ]


def test_source_for_prefers_nrt_then_sp():
    availability = firms.parse_availability(AVAILABILITY)
    assert firms.source_for("VIIRS_SNPP", date(2026, 10, 1), availability) == "VIIRS_SNPP_NRT"
    assert firms.source_for("VIIRS_SNPP", date(2026, 7, 1), availability) == "VIIRS_SNPP_SP"
    assert firms.source_for("VIIRS_SNPP", date(2027, 1, 1), availability) is None


def test_fetch_cells_uses_one_request_per_sensor_when_nrt_covers_the_range():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, text=CSV.splitlines()[0] + "\n")

    availability = firms.parse_availability(AVAILABILITY)
    firms.fetch_cells(make_client(transport=httpx.MockTransport(handler)), "KEY123",
                      date(2026, 8, 30), date(2026, 9, 2), availability)
    assert paths == [
        "/api/area/csv/KEY123/VIIRS_SNPP_NRT/95,-6,120,8/4/2026-08-30",
        "/api/area/csv/KEY123/VIIRS_NOAA20_NRT/95,-6,120,8/4/2026-08-30",
    ]


def test_fetch_cells_switches_to_sp_before_nrt_coverage():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, text="latitude,longitude,acq_date,confidence,frp\n")

    availability = firms.parse_availability(AVAILABILITY)
    firms.fetch_cells(make_client(transport=httpx.MockTransport(handler)), "K", date(2026, 8, 13), date(2026, 8, 16),
                      availability)
    assert paths[:2] == ["/api/area/csv/K/VIIRS_SNPP_SP/95,-6,120,8/2/2026-08-13",
                         "/api/area/csv/K/VIIRS_SNPP_NRT/95,-6,120,8/2/2026-08-15"]


def test_fetch_cells_errors_never_contain_the_key():
    availability = firms.parse_availability(AVAILABILITY)
    with pytest.raises(FetchError) as info:
        firms.fetch_cells(make_client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
                          "KEY123", date(2026, 9, 1), date(2026, 9, 1), availability)
    assert "KEY123" not in str(info.value)
