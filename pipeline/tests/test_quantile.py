import random
from dataclasses import replace
from datetime import date, timedelta

import pytest

from myhaze.features import FEATURES, FeatureRow
from myhaze.model.quantile import contributions, fit, from_text, predict, to_text


def rows_for(n=240, seed=1):
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        fire = rng.random()
        x = dict.fromkeys(FEATURES, None)
        x.update(pm_d0=40 + 60 * rng.random(), upwind_fire=fire * 5, lat=3.0, lon=101.5, region_group=0.0)
        day = date(2026, 7, 1) + timedelta(days=i % 90)
        rows.append(FeatureRow("S", day, 1, day + timedelta(days=1), x, 30 + 100 * fire))
    return rows


def test_fit_predict_orders_quantiles_and_survives_serialisation():
    rows = rows_for()
    boosters = fit(rows, rounds=60)
    preds = predict(boosters, rows[:5])
    assert all(low <= mid <= high for low, mid, high in preds)
    again = predict(from_text(to_text(boosters)), rows[:5])
    assert [v for p in again for v in p] == pytest.approx([v for p in preds for v in p])


def test_more_upwind_fire_never_lowers_the_forecast():
    boosters = fit(rows_for(), rounds=60)
    base = rows_for(1)[0]
    calm = replace(base, x=dict(base.x, upwind_fire=0.5))
    smoky = replace(base, x=dict(base.x, upwind_fire=4.5))
    (_, calm_mid, _), (_, smoky_mid, _) = predict(boosters, [calm, smoky])
    assert smoky_mid >= calm_mid


def test_contributions_cover_every_feature():
    boosters = fit(rows_for(), rounds=30)
    contrib = contributions(boosters[0.5], rows_for(2))
    assert len(contrib) == 2 and set(contrib[0]) == set(FEATURES)
