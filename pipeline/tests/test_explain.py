import math
from datetime import date, timedelta

from myhaze.features import FeatureRow
from myhaze.model.explain import compass, explain

D = date(2026, 10, 15)


def test_explain_ranks_families_and_names_the_fire_region():
    x = {"wind_from_sin": math.sin(math.radians(225)), "wind_from_cos": math.cos(math.radians(225))}
    row = FeatureRow("S", D, 1, D + timedelta(days=1), x, None,
                     {"sumatra": 50.0, "kalimantan": 5.0, "peninsular": 0.0, "my_borneo": 0.0, "other": 0.0})
    contrib = {"upwind_fire": 0.30, "fire_sumatra": 0.05, "rain_mm": -0.12, "pm_d0": 0.02, "wind_from_sin": 0.08}
    assert explain(contrib, row, rain_window="tomorrow afternoon", trapped_window="early tomorrow morning") == [
        "Fires upwind, mainly in Sumatra, are adding smoke.",
        "Rain expected tomorrow afternoon should help clear the air.",
        "Winds from the south-west are carrying smoke in.",
        "Smoke is likely to be trapped near the ground early tomorrow morning.",
    ]


def test_explain_without_contributions_keeps_only_weather_notes():
    row = FeatureRow("S", D, 1, D + timedelta(days=1), {}, None)
    assert explain({}, row, trapped_window="early tomorrow morning") == [
        "Smoke is likely to be trapped near the ground early tomorrow morning."]


def test_compass():
    assert [compass(d) for d in (0, 44, 90, 225, 350)] == ["north", "north-east", "east", "south-west", "north"]


def test_explain_describes_the_regional_smoke_outlook():
    row = FeatureRow("S", D, 1, D + timedelta(days=1), {}, None)
    assert explain({"cams_target": 0.4}, row) == ["Regional smoke forecasts expect more haze to arrive."]
    assert explain({"cams_target": -0.3}, row) == ["Regional smoke forecasts expect the haze to ease."]
