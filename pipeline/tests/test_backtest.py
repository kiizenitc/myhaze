import random
from datetime import date, timedelta

import pytest

from myhaze.features import FEATURES, FeatureRow
from myhaze.model.backtest import choose_method, render_markdown, run_backtest


def synthetic():
    rng = random.Random(3)
    start = date(2026, 7, 1)
    fire = [rng.random() for _ in range(130)]

    def truth(t):
        return 5 + 120 * fire[t]

    rows, cams, daily = [], {}, {}
    for s in range(4):
        sid = f"S{s}"
        for t in range(120):
            day = start + timedelta(days=t)
            daily[(sid, day)] = truth(t)
            cams[(sid, day)] = truth(t) * rng.uniform(0.5, 1.6)
        for t in range(3, 110):
            issue = start + timedelta(days=t)
            for lead in (1, 2):
                x = dict.fromkeys(FEATURES, None)
                x.update(pm_d0=truth(t), upwind_fire=fire[t + lead] * 5, lat=1.0 + s, lon=101.0, region_group=0.0)
                rows.append(FeatureRow(sid, issue, lead, issue + timedelta(days=lead), x, truth(t + lead)))
    return rows, cams, daily


def test_backtest_prefers_a_model_that_beats_both_baselines():
    rows, cams, daily = synthetic()
    report = run_backtest(rows, cams, daily)
    lead1 = report["leads"]["1"]
    assert lead1["model"]["band_accuracy"] > lead1["persistence"]["band_accuracy"]
    assert lead1["model"]["band_accuracy"] > lead1["cams"]["band_accuracy"]
    assert lead1["method"] == "model"
    assert "| Lead |" in render_markdown(report)


def test_backtest_refuses_when_a_window_is_empty():
    rows, cams, daily = synthetic()
    with pytest.raises(ValueError):
        run_backtest([r for r in rows if r.target_day > date(2026, 9, 30)], cams, daily)


def test_choose_method_falls_back_to_the_better_baseline():
    model = {"band_accuracy": 0.70, "pod_unhealthy": 0.95}
    assert choose_method({"model": model, "persistence": {"band_accuracy": 0.80, "pod_unhealthy": 0.9},
                          "cams": {"band_accuracy": 0.60, "pod_unhealthy": 0.9}}) == "persistence"
    assert choose_method({"model": model, "persistence": {"band_accuracy": 0.50, "pod_unhealthy": 0.9},
                          "cams": {"band_accuracy": 0.65, "pod_unhealthy": 0.98}}) == "cams"


def test_a_clearly_better_model_is_not_dropped_over_a_tie_in_unhealthy_days_caught():
    # 19 Oct 2026, tomorrow: CAMS caught 472 of 565 unhealthy days, the model 470, while the model got the band right
    # on 84% of days against 78%
    scores = {"model": {"band_accuracy": 0.8359, "pod_unhealthy": 0.8319},
              "persistence": {"band_accuracy": 0.7318, "pod_unhealthy": 0.7912},
              "cams": {"band_accuracy": 0.7806, "pod_unhealthy": 0.8354}}
    assert choose_method(scores) == "model"


def test_a_model_that_misses_clearly_more_unhealthy_days_is_not_used():
    # 19 Oct 2026, the day after: CAMS caught 82% of unhealthy days, the model 78%
    scores = {"model": {"band_accuracy": 0.7902, "pod_unhealthy": 0.7805},
              "persistence": {"band_accuracy": 0.6498, "pod_unhealthy": 0.7239},
              "cams": {"band_accuracy": 0.7718, "pod_unhealthy": 0.8230}}
    assert choose_method(scores) == "cams"
