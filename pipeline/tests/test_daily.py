from datetime import date, datetime, timedelta, timezone

from myhaze.daily import daily_means, trailing_mean

# 2026-10-14 00:00 MYT is 2026-10-13 16:00 UTC
MYT_MIDNIGHT = datetime(2026, 10, 13, 16, tzinfo=timezone.utc)


def test_daily_means_use_malaysia_days_and_need_18_hours():
    series = {MYT_MIDNIGHT + timedelta(hours=h): 10.0 + (h // 24) * 10 for h in range(24 + 17)}
    assert daily_means(series) == {date(2026, 10, 14): 10.0}


def test_trailing_mean_needs_enough_hours():
    end = MYT_MIDNIGHT + timedelta(hours=30)
    series = {end - timedelta(hours=k): float(k) for k in range(24)}
    assert trailing_mean(series, end) == sum(range(24)) / 24
    assert trailing_mean({end: 5.0}, end) is None
