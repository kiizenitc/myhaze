"""Backtest the model against persistence and corrected CAMS on held-out days, and choose what ships."""
from __future__ import annotations

from datetime import date

from ..baselines import cams_corrected, persistence
from ..features import FeatureRow
from ..metrics import evaluate, meets_target
from .quantile import choose_rounds, fit, predict

TRAIN_END = date(2026, 9, 15)
TUNE_END = date(2026, 9, 30)


def _scores(test: list[FeatureRow], preds, cams_daily, daily_pm) -> dict:
    model, persist, cams = [], [], []
    for row, (low, mid, high) in zip(test, preds):
        p = persistence(row)
        c = cams_corrected(row.station_id, row.issue_day, row.target_day, cams_daily, daily_pm)
        if p is None or c is None:
            continue  # all three methods are scored on exactly the same days
        model.append({"obs": row.y, "p10": low, "p50": mid, "p90": high})
        persist.append({"obs": row.y, "p50": p})
        cams.append({"obs": row.y, "p50": c})
    return {"model": evaluate(model), "persistence": evaluate(persist), "cams": evaluate(cams)}


def _beats(a: dict, b: dict) -> bool:
    return ((a.get("band_accuracy") or 0) >= (b.get("band_accuracy") or 0)
            and (a.get("pod_unhealthy") or 0) >= (b.get("pod_unhealthy") or 0))


def choose_method(scores: dict) -> str:
    if _beats(scores["model"], scores["persistence"]) and _beats(scores["model"], scores["cams"]):
        return "model"
    p, c = scores["persistence"], scores["cams"]
    return "persistence" if (p.get("band_accuracy") or 0) >= (c.get("band_accuracy") or 0) else "cams"


def run_backtest(rows: list[FeatureRow], cams_daily: dict, daily_pm: dict, train_end: date = TRAIN_END,
                 tune_end: date = TUNE_END) -> dict:
    report: dict = {"train_end": train_end.isoformat(), "tune_end": tune_end.isoformat(), "leads": {}}
    for lead in (1, 2):
        labelled = [r for r in rows if r.lead == lead and r.y is not None]
        train = [r for r in labelled if r.target_day <= train_end]
        tune = [r for r in labelled if train_end < r.target_day <= tune_end]
        test = [r for r in labelled if r.target_day > tune_end]
        if not train or not tune or not test:
            raise ValueError(f"lead {lead}: need labelled rows in train/tune/test windows "
                             f"(have {len(train)}/{len(tune)}/{len(test)})")
        rounds = choose_rounds(train, tune)
        scores = _scores(test, predict(fit(train + tune, rounds), test), cams_daily, daily_pm)
        report["leads"][str(lead)] = {
            "rounds": rounds, "n_train": len(train) + len(tune),
            "test_from": min(r.target_day for r in test).isoformat(),
            "test_to": max(r.target_day for r in test).isoformat(),
            **scores, "method": choose_method(scores), "meets_target": meets_target(scores["model"]),
        }
    return report


def _pct(value) -> str:
    return "–" if value is None else f"{value * 100:.1f}%"


def render_markdown(report: dict) -> str:
    lines = ["# MYHaze backtest", "",
             f"Trained on days up to {report['tune_end']}; tested on later days. Bands are the Real Feel "
             "bands (aqicn's US AQI numbers, Malaysia's band names) of each day's average PM2.5. Target for tomorrow: ≥90% correct band and ≥90% of "
             "unhealthy-or-worse days caught.", "",
             "| Lead | Method | Days | Correct band | Unhealthy+ caught | False alarms | Avg miss (µg/m³) | In 80% range |",
             "|---|---|---|---|---|---|---|---|"]
    for lead, entry in report["leads"].items():
        label = "Tomorrow" if lead == "1" else "Day after"
        for method in ("model", "persistence", "cams"):
            s = entry[method]
            chosen = " (shipped)" if entry["method"] == method else ""
            lines.append(f"| {label} | {method}{chosen} | {s['n']} | {_pct(s['band_accuracy'])} | "
                         f"{_pct(s['pod_unhealthy'])} | {_pct(s['far_unhealthy'])} | {s['mae_ugm3']} | "
                         f"{_pct(s['coverage_80'])} |")
    lead1 = report["leads"].get("1", {})
    lines += ["", f"Tomorrow's target met: **{'yes' if lead1.get('meets_target') else 'no'}**."]
    return "\n".join(lines) + "\n"
