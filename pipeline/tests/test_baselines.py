from datetime import date, timedelta

from myhaze.baselines import cams_corrected, persistence
from myhaze.features import FeatureRow

D = date(2026, 10, 10)


def test_persistence_is_the_issue_day_mean():
    row = FeatureRow("S", D, 1, D + timedelta(days=1), {"pm_d0": 61.5}, None)
    assert persistence(row) == 61.5


def test_cams_corrected_scales_by_recent_observed_over_modelled():
    daily_pm = {("S", D - timedelta(days=k)): 60.0 for k in range(7)}
    cams = {("S", D - timedelta(days=k)): 30.0 for k in range(7)}
    cams[("S", D + timedelta(days=1))] = 40.0
    assert cams_corrected("S", D, D + timedelta(days=1), cams, daily_pm) == 80.0
    assert cams_corrected("S", D, D + timedelta(days=2), cams, daily_pm) is None
    assert cams_corrected("S", D, D + timedelta(days=1), cams, {("S", D): 60.0}) is None
