from datetime import date, datetime, timedelta, timezone

import pytest

from myhaze.features import (FEATURES, build_live_rows, build_rows, cell_arrays, live_pm, static_sources,
                             upwind_by_region)
from myhaze.rows import FireCell, HourlyWeather, Station
from myhaze.weather import RAIN_POINTS, WeatherDay

KLANG = Station("CA21B", "Klang", "Selangor", 3.04, 101.45)
KUCHING = Station("CA44Q", "Kuching", "Sarawak", 1.55, 110.35)
ISSUE = date(2026, 10, 10)
SW_WIND = WeatherDay(2.0, 3, 8.0, 15.0, 225.0, 80.0)  # wind blowing from the south-west


def inputs():
    daily_pm = {(s.station_id, ISSUE + timedelta(days=k)): 50.0 + k for s in (KLANG, KUCHING) for k in range(-4, 4)}
    cells = {ISSUE + timedelta(days=k): [FireCell(ISSUE + timedelta(days=k), 1.5, 101.25, 100.0 + k, 3)]
             for k in range(-5, 3)}
    weather = {(p.station_id, ISSUE + timedelta(days=lead), lead): SW_WIND
               for p in (KLANG, KUCHING, *RAIN_POINTS) for lead in (1, 2)}
    return daily_pm, cells, weather


def test_rows_have_every_feature_and_the_target():
    daily_pm, cells, weather = inputs()
    rows = build_rows([KLANG, KUCHING], daily_pm, cells, weather, [ISSUE])
    assert len(rows) == 4 and all(set(r.x) == set(FEATURES) for r in rows)
    klang_1 = next(r for r in rows if r.station_id == "CA21B" and r.lead == 1)
    assert (klang_1.target_day, klang_1.y, klang_1.x["pm_d0"], klang_1.x["pm_d2"]) == (ISSUE + timedelta(days=1), 51.0, 50.0, 48.0)
    assert klang_1.x["upwind_fire"] > 0  # the fire at 1.6N 101.4E is south of Klang, within 90 degrees of a south-west wind


def test_features_do_not_change_when_future_data_changes():
    daily_pm, cells, weather = inputs()
    base = build_rows([KLANG, KUCHING], daily_pm, cells, weather, [ISSUE])
    future_pm = {k: (v * 3 if k[1] > ISSUE else v) for k, v in daily_pm.items()}
    future_cells = {d: ([FireCell(c.day, c.lat_bin, c.lon_bin, c.frp_sum * 10, c.detections) for c in cs] if d >= ISSUE else cs)
                    for d, cs in cells.items()}
    again = build_rows([KLANG, KUCHING], future_pm, future_cells, weather, [ISSUE])
    assert [r.x for r in base] == [r.x for r in again]
    assert [r.y for r in base] != [r.y for r in again]


def test_upwind_counts_only_fires_the_wind_blows_from():
    arrays = cell_arrays([FireCell(ISSUE, 1.5, 101.25, 100.0, 1)])  # south of Klang, in Sumatra
    assert sum(upwind_by_region(KLANG, arrays, 225.0).values()) > 0
    assert sum(upwind_by_region(KLANG, arrays, 45.0).values()) == 0
    assert upwind_by_region(KLANG, arrays, 225.0)["sumatra"] > 0
    assert sum(upwind_by_region(KLANG, None, 225.0).values()) == 0


def test_live_rows_use_the_current_reading_and_the_live_forecast():
    daily_pm, cells, _ = inputs()
    now = datetime(2026, 10, 10, 2, tzinfo=timezone.utc)  # 10:00 MYT on the issue day
    start = datetime(2026, 10, 9, 16, tzinfo=timezone.utc)
    times = [start + timedelta(hours=h) for h in range(96)]
    hw = {p.station_id: HourlyWeather(p.station_id, times, [0.1] * 96, [400.0] * 96, [5.0] * 96, [12.0] * 96,
                                      [225.0] * 96, [75.0] * 96) for p in (KLANG, *RAIN_POINTS)}
    past_pm = {k: v for k, v in daily_pm.items() if k[1] <= ISSUE}  # live: nothing after today exists yet
    rows = build_live_rows([KLANG], now, {"CA21B": 88.0}, past_pm, cells, hw)
    assert [(r.lead, r.x["pm_d0"], r.y) for r in rows] == [(1, 88.0, None), (2, 88.0, None)]
    assert rows[0].x["wind_from_sin"] == pytest.approx(-0.7071, abs=1e-3)


def test_cams_features_use_the_target_forecast_and_the_recent_error_ratio():
    import math

    daily_pm, cells, weather = inputs()
    cams = {(s.station_id, ISSUE - timedelta(days=k)): 25.0 for s in (KLANG, KUCHING) for k in range(7)}
    cams.update({(s.station_id, ISSUE + timedelta(days=lead)): 40.0 for s in (KLANG, KUCHING) for lead in (1, 2)})
    rows = build_rows([KLANG, KUCHING], daily_pm, cells, weather, [ISSUE], cams_daily=cams)
    klang_1 = next(r for r in rows if r.station_id == "CA21B" and r.lead == 1)
    observed = sum(daily_pm[("CA21B", ISSUE - timedelta(days=k))] for k in range(5))  # pm history covers 5 days
    assert klang_1.x["cams_target"] == pytest.approx(math.log1p(40.0))
    assert klang_1.x["cams_ratio"] == pytest.approx(observed / (25.0 * 5))
    assert build_rows([KLANG], daily_pm, cells, weather, [ISSUE])[0].x["cams_target"] is None


def test_static_sources_are_malaysian_cells_burning_on_most_days():
    days = [ISSUE - timedelta(days=k) for k in range(20)]
    kerteh = [FireCell(d, 4.5, 103.25, 20.0, 1) for d in days]  # the gas flare at the Kerteh refinery
    riau = [FireCell(d, 1.0, 101.5, 300.0, 9) for d in days]  # a Sumatran peat fire: just as steady, but real smoke
    farm = [FireCell(days[0], 3.0, 101.5, 5.0, 1)]  # a one-off burn in Selangor
    assert static_sources(kerteh + riau + farm) == {(4.5, 103.25)}
    assert static_sources(kerteh[:5]) == set()  # too few days to tell a flare from a fire


def live_weather(start):
    times = [start + timedelta(hours=h) for h in range(96)]
    return {p.station_id: HourlyWeather(p.station_id, times, [0.0] * 96, [400.0] * 96, [5.0] * 96, [12.0] * 96,
                                        [225.0] * 96, [75.0] * 96) for p in (KLANG, *RAIN_POINTS)}


def test_live_rows_use_the_last_complete_utc_fire_day_and_fall_back_when_firms_is_late():
    import math

    now = datetime(2026, 10, 10, 17, tzinfo=timezone.utc)  # 01:00 MYT on 11 Oct: 10 Oct (UTC) is still burning
    hw = live_weather(datetime(2026, 10, 10, 16, tzinfo=timezone.utc))
    day = lambda d: date(2026, 10, d)
    cells = {day(9): [FireCell(day(9), 1.5, 101.25, 100.0, 3)], day(10): [FireCell(day(10), 1.5, 101.25, 999.0, 3)]}
    rows = build_live_rows([KLANG], now, {"CA21B": 60.0}, {}, cells, hw)
    assert rows[0].x["fire_sumatra"] == pytest.approx(math.log1p(100.0))
    late = {day(7): [FireCell(day(7), 1.5, 101.25, 50.0, 3)], day(10): cells[day(10)]}  # nothing yet for 8-9 Oct
    rows = build_live_rows([KLANG], now, {"CA21B": 60.0}, {}, late, hw)
    assert rows[0].x["fire_sumatra"] == pytest.approx(math.log1p(50.0))


def test_live_daily_pm_takes_todays_value_from_the_live_reading():
    daily = {("S", ISSUE - timedelta(days=1)): 40.0, ("S", ISSUE): 12.0, ("S", ISSUE + timedelta(days=1)): 99.0}
    assert live_pm(daily, {"S": 70.0}, ISSUE) == {("S", ISSUE - timedelta(days=1)): 40.0, ("S", ISSUE): 70.0}
