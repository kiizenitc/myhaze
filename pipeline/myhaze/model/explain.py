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


def _fires(worse: bool, row: FeatureRow, contrib: dict[str, float], effect: float) -> str:
    """Upwind smoke when the upwind index drives the effect; otherwise the regional fire count that does."""
    if contrib.get("upwind_fire", 0.0) / effect >= 0.5:
        if not worse:
            return "Few fires are upwind right now."
        upwind = row.upwind_by_region or {}
        total = sum(upwind.values())
        region = max(upwind, key=upwind.get) if total > 0 else None
        where = f", mainly in {REGION_NAMES[region]}," if region in REGION_NAMES and upwind[region] >= 0.5 * total else ""
        return f"Fires upwind{where} are adding smoke."
    if not worse:
        return "Few fires are burning in the region right now."
    region = max(REGION_NAMES, key=lambda r: contrib.get(f"fire_{r}", 0.0))
    if contrib.get(f"fire_{region}", 0.0) > contrib.get("fire_trend", 0.0):
        return f"Many fires are burning in {REGION_NAMES[region]}."
    return "Fire activity in the region is rising."


def _sentence(family: str, worse: bool, row: FeatureRow, contrib: dict[str, float], effect: float,
              rain_window: str | None) -> str | None:
    x = row.x
    if family == "persistence":
        trend = x.get("pm_trend")
        if trend is None or (trend > 0) != worse:
            return None  # a high level alone is not a trend: say nothing rather than something untrue
        return "Haze has been building over the last few days." if worse else \
            "The air has been improving over the last few days."
    if family == "fires":
        return _fires(worse, row, contrib, effect)
    if family == "rain":
        if worse:
            return "Little rain is expected to wash the smoke out."
        return f"Rain expected {rain_window} should help clear the air." if rain_window else \
            "Rain on the way should help clear the air."
    if family == "outlook":
        cams, today = x.get("cams_target"), x.get("pm_d0")
        if cams is None or today is None or (cams > math.log1p(today)) != worse:
            return None
        return "Regional smoke forecasts expect more haze to arrive." if worse else \
            "Regional smoke forecasts expect the haze to ease."
    if family == "wind":
        s, c = x.get("wind_from_sin"), x.get("wind_from_cos")
        if s is None or c is None:
            return None
        direction = compass(math.degrees(math.atan2(s, c)))
        return f"Winds from the {direction} are carrying smoke in." if worse else \
            f"Winds from the {direction} are bringing cleaner air."
    return None


def explain(contrib: dict[str, float], row: FeatureRow, *, rain_window: str | None = None,
            trapped_window: str | None = None, limit: int = 3, direction: int = 0) -> list[str]:
    """Up to `limit` reasons, strongest first. direction is +1 when tomorrow looks worse than now, -1 when better
    and 0 when about the same; reasons pushing the other way are left out so the list never argues with the forecast."""
    totals = {family: sum(contrib.get(f, 0.0) for f in features) for family, features in FAMILIES.items()}
    sentences: list[str] = []
    for family, effect in sorted(totals.items(), key=lambda item: -abs(item[1])):
        if abs(effect) < MIN_EFFECT or len(sentences) >= limit:
            continue
        if direction and (effect > 0) != (direction > 0):
            continue
        sentence = _sentence(family, effect > 0, row, contrib, effect, rain_window)
        if sentence:
            sentences.append(sentence)
    if trapped_window:
        sentences.append(f"Smoke is likely to be trapped near the ground {trapped_window}.")
    return sentences
