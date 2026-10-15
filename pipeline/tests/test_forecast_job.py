from datetime import datetime, timedelta, timezone

from myhaze.jobs.forecast import forecast_levels, forecast_station, pm_now
from myhaze.model.quantile import fit, to_text
from myhaze.publish import validate_station
from myhaze.rows import Station
from tests.test_quantile import rows_for

NOW = datetime(2026, 10, 15, 2, tzinfo=timezone.utc)  # 10:00 MYT
KLANG = Station("CA21B", "Klang", "Selangor", 3.04, 101.45)


def test_station_payload_without_hourly_feed_is_estimated():
    payload = forecast_station(KLANG, NOW, NOW, {}, (NOW, 150.0), None, None, "persistence", None, None, {})
    validate_station(payload)
    assert payload["estimated"] is True
    assert payload["now"]["real_feel"] is None and payload["now"]["official_api"] == 150
    assert payload["why"] == []


def test_forecast_without_a_model_falls_back_to_persistence():
    observed = {NOW - timedelta(hours=k): 60.0 for k in range(24)}
    assert pm_now(observed, None, NOW) == (60.0, True)
    levels, contribs, methods = forecast_levels(rows_for(4), None, {}, {})
    assert levels == {} and contribs == {} and set(methods.values()) == {"persistence"}
    payload = forecast_station(KLANG, NOW, NOW, observed, (NOW, 140.0), None, None, "persistence", None, None, {})
    validate_station(payload)
    assert payload["method"] == "persistence" and payload["estimated"] is False
    assert payload["hours"][0]["pm25"] == 60.0


def test_forecast_levels_use_the_shipped_model():
    rows = rows_for(240)
    texts = to_text(fit(rows, rounds=40))
    model = ({1: "model", 2: "persistence"}, {}, {1: texts})
    live = rows_for(3)
    levels, contribs, methods = forecast_levels(live, model, {}, {})
    assert set(levels["S"]) == {1} and len(levels["S"][1]) == 3
    assert "upwind_fire" in contribs["S"] and methods["S"] == "model"


def test_a_live_reading_means_not_estimated_even_before_a_full_day_of_hourly_data():
    observed = {NOW - timedelta(hours=k): 80.0 for k in range(3)}  # the archive is only 3 hours old
    payload = forecast_station(KLANG, NOW, NOW, observed, (NOW, 140.0), None, None, "persistence", None, None, {})
    assert payload["estimated"] is False and payload["now"]["real_feel"] is not None
