from datetime import date, datetime, timedelta, timezone

import pytest

from myhaze.model.closure import closure_indicator, next_school_day, p_above


def test_next_school_day_respects_state_weeks():
    friday_evening = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)  # Fri 20:00 MYT
    assert next_school_day(friday_evening, "Selangor") == date(2026, 10, 19)  # Monday
    assert next_school_day(friday_evening, "Kedah") == date(2026, 10, 18)     # Sunday: Sun–Thu school week
    early_thursday = datetime(2026, 10, 14, 22, tzinfo=timezone.utc)          # Thu 06:00 MYT
    assert next_school_day(early_thursday, "Johor") == date(2026, 10, 15)


def test_p_above():
    assert p_above(180, 150, 216, 180) == pytest.approx(0.5, abs=0.01)
    assert p_above(100, 90, 110, 180) < 0.01
    assert p_above(200, None, None, 180) == 1.0


def test_closure_indicator_uses_the_three_day_rule_with_observed_days():
    now = datetime(2026, 10, 15, 2, tzinfo=timezone.utc)  # Thu 10:00 MYT, so the next school day is Friday
    times = [now + timedelta(hours=h) for h in range(48)]
    official = ([150.0] * 48, [160.0] * 48, [170.0] * 48)
    streak = closure_indicator("Selangor", now, times, official, {date(2026, 10, 14): 155, date(2026, 10, 15): 158})
    assert (streak["school_day"], streak["rule"]) == ("2026-10-16", "three_days_above_150")
    assert streak["probability"] > 0.9
    broken = closure_indicator("Selangor", now, times, official, {date(2026, 10, 14): 140, date(2026, 10, 15): 158})
    assert broken["rule"] == "api_above_180" and broken["probability"] < 0.05


def test_closure_indicator_beyond_the_horizon_has_no_probability():
    friday_evening = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
    times = [friday_evening + timedelta(hours=h) for h in range(48)]  # ends Sunday 20:00 MYT
    result = closure_indicator("Selangor", friday_evening, times, ([1.0] * 48,) * 3, {})
    assert result == {"school_day": "2026-10-19", "probability": None, "rule": None}


def test_closure_needs_most_of_the_school_day_inside_the_forecast():
    saturday_morning = datetime(2026, 10, 17, 0, tzinfo=timezone.utc)  # Sat 08:00 MYT: Monday is next in Selangor
    times = [saturday_morning + timedelta(hours=h) for h in range(48)]  # ends Mon 07:00 MYT
    result = closure_indicator("Selangor", saturday_morning, times, ([150.0] * 48, [200.0] * 48, [250.0] * 48), {})
    assert result == {"school_day": "2026-10-19", "probability": None, "rule": None}
