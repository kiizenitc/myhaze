from datetime import date, datetime, timedelta, timezone

import pytest

from myhaze.convert import ugm3_to_api
from myhaze.model.hourly import build_path, official_api_path
from myhaze.rows import HourlyWeather

NOW = datetime(2026, 10, 15, 2, tzinfo=timezone.utc)  # 10:00 MYT, Thursday
DAYS = (date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 17))
FLAT = {d: (50.0, 50.0, 50.0) for d in DAYS}


def weather(blh_for_local_hour=lambda h: 500.0, rain_at=()):
    start = datetime(2026, 10, 14, 16, tzinfo=timezone.utc)  # 00:00 MYT on the 15th
    times = [start + timedelta(hours=h) for h in range(96)]
    local_hour = [(t + timedelta(hours=8)).hour for t in times]
    return HourlyWeather("S", times, [5.0 if t in rain_at else 0.0 for t in times],
                         [blh_for_local_hour(h) for h in local_hour], [3.0] * 96, [10.0] * 96, [225.0] * 96,
                         [80.0] * 96)


def test_path_starts_at_the_live_reading_and_relaxes_to_the_model():
    levels = {DAYS[0]: (40.0, 50.0, 70.0), DAYS[1]: (60.0, 80.0, 110.0), DAYS[2]: (50.0, 70.0, 100.0)}
    path = build_path(NOW, levels, weather(), anchor=100.0)
    assert len(path.times) == 48 and path.times[0] == NOW
    assert path.p10[0] == path.p50[0] == path.p90[0] == pytest.approx(100.0)
    tomorrow_noon = path.times.index(datetime(2026, 10, 16, 4, tzinfo=timezone.utc))
    assert path.p50[tomorrow_noon] == pytest.approx(80.0, rel=0.02)
    assert path.p10[tomorrow_noon] < path.p50[tomorrow_noon] < path.p90[tomorrow_noon]


def test_shallow_mornings_raise_and_rain_lowers_the_path():
    shallow = weather(lambda h: 100.0 if 6 <= h <= 9 else 1000.0)
    path = build_path(NOW, FLAT, shallow, anchor=None)
    morning = path.times.index(datetime(2026, 10, 15, 23, tzinfo=timezone.utc))  # 07:00 MYT on the 16th
    midday = path.times.index(datetime(2026, 10, 16, 5, tzinfo=timezone.utc))    # 13:00 MYT
    assert path.p50[morning] > path.p50[midday] and path.trapped[morning] and not path.trapped[midday]

    rain_hour = datetime(2026, 10, 16, 5, tzinfo=timezone.utc)
    wet = build_path(NOW, FLAT, weather(lambda h: 100.0 if 6 <= h <= 9 else 1000.0, rain_at=(rain_hour,)), None)
    assert wet.p50[midday] == pytest.approx(path.p50[midday] * 0.85, rel=1e-3)


def test_official_api_is_a_24_hour_mean_of_observed_and_forecast():
    path = build_path(NOW, FLAT, None, anchor=None)
    observed = {NOW - timedelta(hours=k): 100.0 for k in range(1, 24)}
    low, mid, high = official_api_path(path, observed, fallback=None)
    assert mid[0] == pytest.approx(ugm3_to_api((23 * 100.0 + 50.0) / 24), abs=0.1)
    assert mid[23] == pytest.approx(ugm3_to_api(50.0), abs=0.1)
    assert len(low) == len(high) == 48
