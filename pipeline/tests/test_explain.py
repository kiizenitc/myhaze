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
    rising = FeatureRow("S", D, 1, D + timedelta(days=1), {"pm_d0": 30.0, "cams_target": math.log1p(60.0)}, None)
    easing = FeatureRow("S", D, 1, D + timedelta(days=1), {"pm_d0": 80.0, "cams_target": math.log1p(40.0)}, None)
    assert explain({"cams_target": 0.4}, rising) == ["Regional smoke forecasts expect more haze to arrive."]
    assert explain({"cams_target": -0.3}, easing) == ["Regional smoke forecasts expect the haze to ease."]


def test_the_outlook_is_not_claimed_when_the_smoke_forecast_says_otherwise():
    easing = FeatureRow("S", D, 1, D + timedelta(days=1), {"pm_d0": 80.0, "cams_target": math.log1p(40.0)}, None)
    assert explain({"cams_target": 0.4}, easing) == []
    assert explain({"cams_target": 0.4}, FeatureRow("S", D, 1, D, {}, None)) == []


def test_haze_building_is_said_only_when_readings_actually_rose():
    rose = FeatureRow("S", D, 1, D + timedelta(days=1), {"pm_d0": 80.0, "pm_trend": 0.3}, None)
    fell = FeatureRow("S", D, 1, D + timedelta(days=1), {"pm_d0": 80.0, "pm_trend": -0.2}, None)
    assert explain({"pm_d0": 0.3}, rose) == ["Haze has been building over the last few days."]
    assert explain({"pm_d0": 0.3}, fell) == []
    assert explain({"pm_d0": -0.3}, fell) == ["The air has been improving over the last few days."]


def test_reasons_pointing_the_other_way_from_the_forecast_are_left_out():
    row = FeatureRow("S", D, 1, D + timedelta(days=1), {}, None, {"sumatra": 50.0, "kalimantan": 0.0})
    contrib = {"upwind_fire": 0.30, "rain_mm": -0.12}
    assert explain(contrib, row, direction=-1) == ["Rain on the way should help clear the air."]
    assert explain(contrib, row, direction=1) == ["Fires upwind, mainly in Sumatra, are adding smoke."]
    assert len(explain(contrib, row, direction=0)) == 2


def test_a_fire_region_is_named_only_when_it_dominates_the_upwind_smoke():
    spread = FeatureRow("S", D, 1, D + timedelta(days=1), {}, None, {"sumatra": 40.0, "kalimantan": 35.0, "other": 25.0})
    assert explain({"upwind_fire": 0.3}, spread) == ["Fires upwind are adding smoke."]
    assert explain({"fire_kalimantan": 0.25, "upwind_fire": 0.02}, spread) == ["Many fires are burning in Kalimantan."]
