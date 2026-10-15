from datetime import date, datetime, timedelta, timezone

import pytest

from myhaze.rows import HourlyWeather
from myhaze.weather import circular_mean_deg, daily_weather

MYT_MIDNIGHT = datetime(2026, 10, 13, 16, tzinfo=timezone.utc)  # 00:00 MYT on 14 Oct


def test_daily_weather_sums_rain_counts_wet_hours_and_averages_wind():
    times = [MYT_MIDNIGHT + timedelta(hours=h) for h in range(24)]
    hw = HourlyWeather("S", times, precip=[1.0 if h < 3 else 0.0 for h in range(24)], blh=[None] * 24,
                       wind10=[4.0] * 24, wind120=[10.0] * 24, wind120_from=[350.0 if h % 2 else 10.0 for h in range(24)],
                       rh=[80.0] * 24)
    day = daily_weather(hw)[date(2026, 10, 14)]
    assert (day.precip_mm, day.wet_hours, day.wind10_kmh, day.rh_mean) == (3.0, 3, 4.0, 80.0)
    assert day.wind120_from_deg == pytest.approx(0.0, abs=0.01) or day.wind120_from_deg == pytest.approx(360.0, abs=0.01)


def test_daily_weather_skips_days_with_too_few_hours():
    times = [MYT_MIDNIGHT + timedelta(hours=h) for h in range(10)]
    hw = HourlyWeather("S", times, [0.0] * 10, [None] * 10, [1.0] * 10, [1.0] * 10, [90.0] * 10, [50.0] * 10)
    assert daily_weather(hw) == {}


def test_circular_mean_handles_missing_and_calm():
    assert circular_mean_deg([90, None, 90], [5, 5, None]) == pytest.approx(90.0)
    assert circular_mean_deg([None], [1]) is None
