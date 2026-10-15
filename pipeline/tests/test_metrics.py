import pytest

from myhaze.convert import api_to_ugm3
from myhaze.metrics import evaluate, meets_target


def rec(obs_api, pred_api, low_api=None, high_api=None):
    r = {"obs": api_to_ugm3(obs_api), "p50": api_to_ugm3(pred_api)}
    if low_api is not None:
        r.update(p10=api_to_ugm3(low_api), p90=api_to_ugm3(high_api))
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
