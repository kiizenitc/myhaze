"""Forecast scores on the official API scale: the band people see, and whether bad days were caught."""
from __future__ import annotations

from .convert import band, ugm3_to_api

OK_BANDS = ("good", "moderate")


def evaluate(records: list[dict]) -> dict:
    rows = [r for r in records if r.get("obs") is not None and r.get("p50") is not None]
    if not rows:
        return {"n": 0, "band_accuracy": None, "unhealthy_days": 0, "pod_unhealthy": None, "far_unhealthy": None,
                "mae_ugm3": None, "coverage_80": None}
    obs_bands = [band(ugm3_to_api(r["obs"])) for r in rows]
    pred_bands = [band(ugm3_to_api(r["p50"])) for r in rows]
    obs_bad = [b not in OK_BANDS for b in obs_bands]
    pred_bad = [b not in OK_BANDS for b in pred_bands]
    caught = sum(p and o for p, o in zip(pred_bad, obs_bad))
    false_alarms = sum(p and not o for p, o in zip(pred_bad, obs_bad))
    bad_days = sum(obs_bad)
    ranged = [r for r in rows if r.get("p10") is not None and r.get("p90") is not None]
    return {
        "n": len(rows),
        "band_accuracy": round(sum(p == o for p, o in zip(pred_bands, obs_bands)) / len(rows), 4),
        "unhealthy_days": bad_days,
        "pod_unhealthy": round(caught / bad_days, 4) if bad_days else None,
        "far_unhealthy": round(false_alarms / (caught + false_alarms), 4) if caught + false_alarms else None,
        "mae_ugm3": round(sum(abs(r["p50"] - r["obs"]) for r in rows) / len(rows), 2),
        "coverage_80": round(sum(r["p10"] <= r["obs"] <= r["p90"] for r in ranged) / len(ranged), 4) if ranged else None,
    }


def meets_target(scores: dict) -> bool:
    return (scores.get("band_accuracy") or 0) >= 0.90 and (scores.get("pod_unhealthy") or 0) >= 0.90
