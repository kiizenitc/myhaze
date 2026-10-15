"""Plain-language reasons for a forecast, from the model's per-feature contributions."""
from __future__ import annotations

import math

from ..features import FeatureRow

FAMILIES = {
    "fires": ("upwind_fire", "fire_sumatra", "fire_kalimantan", "fire_peninsular", "fire_my_borneo", "fire_trend"),
    "rain": ("rain_mm", "wet_hours", "rain_fire_regions"),
    "wind": ("wind10_kmh", "wind120_kmh", "wind_from_sin", "wind_from_cos"),
    "persistence": ("pm_d0", "pm_d1", "pm_d2", "pm_trend", "region_pm_d0"),
    "outlook": ("cams_target", "cams_ratio"),
}
REGION_NAMES = {"sumatra": "Sumatra", "kalimantan": "Kalimantan", "peninsular": "Peninsular Malaysia",
                "my_borneo": "Sarawak and Sabah"}
COMPASS = ("north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west")
MIN_EFFECT = 0.05  # on log1p(PM2.5): about a 5% change


def compass(deg: float) -> str:
    return COMPASS[int(((deg % 360) + 22.5) // 45) % 8]


def _sentence(family: str, worse: bool, row: FeatureRow, rain_window: str | None) -> str | None:
    if family == "persistence":
        return "Haze has been building over the last few days." if worse else \
            "The air has been improving over the last few days."
    if family == "fires":
        if not worse:
            return "Few fires are upwind right now."
        upwind = row.upwind_by_region or {}
        region = max(upwind, key=upwind.get) if upwind and max(upwind.values()) > 0 else None
        where = f", mainly in {REGION_NAMES[region]}," if region in REGION_NAMES else ""
        return f"Fires upwind{where} are adding smoke."
    if family == "rain":
        if worse:
            return "Little rain is expected to wash the smoke out."
        return f"Rain expected {rain_window} should help clear the air." if rain_window else \
            "Rain on the way should help clear the air."
    if family == "outlook":
        return "Regional smoke forecasts expect more haze to arrive." if worse else \
            "Regional smoke forecasts expect the haze to ease."
    if family == "wind":
        s, c = row.x.get("wind_from_sin"), row.x.get("wind_from_cos")
        if s is None or c is None:
            return None
        direction = compass(math.degrees(math.atan2(s, c)))
        return f"Winds from the {direction} are carrying smoke in." if worse else \
            f"Winds from the {direction} are bringing cleaner air."
    return None


def explain(contrib: dict[str, float], row: FeatureRow, *, rain_window: str | None = None,
            trapped_window: str | None = None, limit: int = 3) -> list[str]:
    totals = {family: sum(contrib.get(f, 0.0) for f in features) for family, features in FAMILIES.items()}
    sentences: list[str] = []
    for family, effect in sorted(totals.items(), key=lambda item: -abs(item[1])):
        if abs(effect) < MIN_EFFECT or len(sentences) >= limit:
            continue
        sentence = _sentence(family, effect > 0, row, rain_window)
        if sentence:
            sentences.append(sentence)
    if trapped_window:
        sentences.append(f"Smoke is likely to be trapped near the ground {trapped_window}.")
    return sentences
