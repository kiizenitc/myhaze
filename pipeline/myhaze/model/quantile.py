"""LightGBM models of daily-mean PM2.5 (low / middle / high), trained on log1p(µg/m³)."""
from __future__ import annotations

import lightgbm as lgb
import numpy as np

from ..features import FEATURES, MONOTONE, FeatureRow

QUANTILES = (0.1, 0.5, 0.9)
DEFAULT_ROUNDS = 300
PARAMS = {
    "learning_rate": 0.05, "num_leaves": 15, "min_data_in_leaf": 30,
    "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 1.0,
    "verbose": -1, "seed": 7, "deterministic": True, "num_threads": 1,
}


def _params(q: float) -> dict:
    """LightGBM forbids monotone constraints with the quantile objective, so the middle forecast (which sets the
    bands and the explanations) is a least-squares fit on log1p(PM2.5) with the physical constraints; the range
    edges are unconstrained quantile fits."""
    if q == 0.5:
        return dict(PARAMS, objective="regression", monotone_constraints=[MONOTONE.get(f, 0) for f in FEATURES])
    return dict(PARAMS, objective="quantile", alpha=q)


def matrix(rows: list[FeatureRow]) -> np.ndarray:
    return np.array([[np.nan if r.x.get(f) is None else float(r.x[f]) for f in FEATURES] for r in rows],
                    dtype=float).reshape(len(rows), len(FEATURES))


def _dataset(rows: list[FeatureRow], reference: lgb.Dataset | None = None) -> lgb.Dataset:
    labelled = [r for r in rows if r.y is not None]
    if not labelled:
        raise ValueError("no labelled rows")
    return lgb.Dataset(matrix(labelled), label=np.log1p([r.y for r in labelled]), feature_name=list(FEATURES),
                       categorical_feature=["region_group"], reference=reference, free_raw_data=False)


def choose_rounds(train_rows: list[FeatureRow], tune_rows: list[FeatureRow], max_rounds: int = 600) -> int:
    train = _dataset(train_rows)
    tune = _dataset(tune_rows, reference=train)
    booster = lgb.train(_params(0.5), train, num_boost_round=max_rounds, valid_sets=[tune],
                        callbacks=[lgb.early_stopping(30, verbose=False)])
    return max(booster.best_iteration or DEFAULT_ROUNDS, 20)


def fit(rows: list[FeatureRow], rounds: int = DEFAULT_ROUNDS) -> dict[float, lgb.Booster]:
    data = _dataset(rows)
    return {q: lgb.train(_params(q), data, num_boost_round=rounds) for q in QUANTILES}


def predict(boosters: dict[float, lgb.Booster], rows: list[FeatureRow]) -> list[tuple[float, float, float]]:
    if not rows:
        return []
    x = matrix(rows)
    columns = [np.expm1(boosters[q].predict(x)) for q in QUANTILES]
    return [tuple(sorted(max(float(v), 0.0) for v in triple)) for triple in zip(*columns)]


def contributions(booster: lgb.Booster, rows: list[FeatureRow]) -> list[dict[str, float]]:
    """Per-feature effect on log1p(PM2.5) for each row (LightGBM's built-in SHAP values, bias column dropped)."""
    if not rows:
        return []
    values = booster.predict(matrix(rows), pred_contrib=True)
    return [dict(zip(FEATURES, (float(v) for v in row[:-1]))) for row in values]


def to_text(boosters: dict[float, lgb.Booster]) -> dict[float, str]:
    return {q: b.model_to_string() for q, b in boosters.items()}


def from_text(texts: dict[float, str]) -> dict[float, lgb.Booster]:
    return {float(q): lgb.Booster(model_str=t) for q, t in texts.items()}
