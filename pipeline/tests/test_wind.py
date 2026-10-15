from datetime import datetime, timedelta, timezone

from myhaze import wind
from myhaze.rows import HourlyWeather

NOW = datetime(2026, 10, 15, 10, tzinfo=timezone.utc)


def test_grid_covers_sumatra_the_peninsula_and_borneo_at_one_degree():
    points = wind.grid_points()
    assert len(points) == wind.NX * wind.NY == 27 * 17
    assert (points[0].lat, points[0].lon) == (-7.0, 95.0)  # row by row from the south-west corner
    assert (points[1].lat, points[1].lon) == (-7.0, 96.0)
    assert (points[-1].lat, points[-1].lon) == (9.0, 121.0)
    assert len({p.station_id for p in points}) == len(points)


def test_wind_from_the_south_west_blows_towards_the_north_east():
    assert wind.to_uv(36.0, 225.0) == (7.1, 7.1)  # 10 m/s
    assert wind.to_uv(18.0, 90.0) == (-5.0, 0.0)  # from the east: blowing west
    assert wind.to_uv(None, 90.0) == (None, None)
    assert wind.to_uv(10.0, None) == (None, None)


def test_hourly_field_lists_every_grid_point_in_grid_order_with_gaps_as_null():
    times = [NOW + timedelta(hours=h) for h in range(2)]
    first, second = wind.grid_points()[:2]
    weather = [HourlyWeather(first.station_id, times, [None] * 2, [None] * 2, [None] * 2, [36.0, 18.0], [225.0, 90.0],
                             [None] * 2)]
    field = wind.hourly_field(weather)
    assert field["times"] == ["2026-10-15T10:00:00Z", "2026-10-15T11:00:00Z"]
    assert len(field["u"]) == 2 and len(field["u"][0]) == wind.NX * wind.NY
    assert (field["u"][0][0], field["v"][0][0], field["u"][1][0]) == (7.1, 7.1, -5.0)
    assert field["u"][0][1] is None and field["v"][1][1] is None  # the second point had no data


def test_wind_json_has_frames_every_three_hours_for_the_next_48_hours():
    from myhaze.publish import wind_payload

    hours = [NOW - timedelta(hours=2) + timedelta(hours=h) for h in range(72)]
    field = {"times": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in hours],
             "u": [[float(h)] for h in range(72)], "v": [[0.0] for _ in range(72)]}
    got = wind_payload(field, NOW, NOW)
    assert got["grid"] == {"lon0": 95.0, "lat0": -7.0, "dlon": 1.0, "dlat": 1.0, "nx": 27, "ny": 17}
    assert len(got["times"]) == 16
    assert got["times"][0] == "2026-10-15T10:00:00Z" and got["times"][-1] == "2026-10-17T07:00:00Z"
    assert got["u"][0] == [2.0] and got["u"][1] == [5.0]  # NOW is the field's third hour
