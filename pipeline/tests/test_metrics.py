import pytest

from myhaze.convert import aqicn_aqi_to_ugm3 as real_feel_to_ugm3
from myhaze.metrics import evaluate, meets_target


def rec(obs_rf, pred_rf, low_rf=None, high_rf=None):
    r = {"obs": real_feel_to_ugm3(obs_rf), "p50": real_feel_to_ugm3(pred_rf)}
    if low_rf is not None:
        r.update(p10=real_feel_to_ugm3(low_rf), p90=real_feel_to_ugm3(high_rf))
    return r


def test_evaluate_scores_bands_detection_and_coverage():
    scores = evaluate([rec(150, 160, 120, 190), rec(150, 90, 70, 110), rec(60, 70, 50, 90), rec(40, 120, 100, 140)])
    assert scores["n"] == 4
    assert scores["band_accuracy"] == pytest.approx(0.5)
    assert (scores["unhealthy_days"], scores["pod_unhealthy"]) == (2, 0.5)
    assert scores["far_unhealthy"] == pytest.approx(0.5)
    assert scores["coverage_80"] == pytest.approx(0.5)


def test_evaluate_without_unhealthy_days_has_no_pod():
    scores = evaluate([rec(40, 45), rec(60, 55)])
    assert scores["pod_unhealthy"] is None and scores["coverage_80"] is None and scores["band_accuracy"] == 1.0


def test_meets_target_needs_both_bars():
    assert meets_target({"band_accuracy": 0.92, "pod_unhealthy": 0.91})
    assert not meets_target({"band_accuracy": 0.95, "pod_unhealthy": 0.80})
    assert not meets_target({"band_accuracy": 0.95, "pod_unhealthy": None})


def test_days_are_scored_on_the_real_feel_scale():
    # 42 µg/m³ is Real Feel 117 (unhealthy) though DOE's own table calls it moderate
    scores = evaluate([{"obs": 42.0, "p50": 42.0}])
    assert (scores["unhealthy_days"], scores["pod_unhealthy"]) == (1, 1.0)
