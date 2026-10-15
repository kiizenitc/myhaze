from datetime import date, datetime, timedelta, timezone

from myhaze.features import FeatureRow
from myhaze.jobs import forecast
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


def test_the_official_api_starts_from_does_own_figure():
    observed = {NOW - timedelta(hours=k): 60.0 for k in range(24)}
    payload = forecast_station(KLANG, NOW, NOW, observed, (NOW, 150.0), None, None, "persistence", None, None, {})
    assert payload["hours"][0]["official_api"] == 150


def test_a_station_never_vanishes_while_any_forecast_exists():
    from_model = forecast_station(KLANG, NOW, NOW, {}, None, None, {1: (20.0, 30.0, 45.0)}, "model", None, None, {})
    assert from_model["estimated"] is True and from_model["hours"][0]["pm25"] == 30.0
    from_cams = forecast_station(KLANG, NOW, NOW, {}, None, None, None, "persistence", None, None, {}, cams_today=25.0)
    assert from_cams["hours"][0]["pm25"] == 25.0
    assert forecast_station(KLANG, NOW, NOW, {}, None, None, None, "persistence", None, None, {}) is None


def test_why_keeps_only_reasons_that_match_the_forecast_direction():
    observed = {NOW - timedelta(hours=k): 80.0 for k in range(24)}
    row = FeatureRow("CA21B", date(2026, 10, 15), 1, date(2026, 10, 16), {}, None, {"sumatra": 50.0})
    payload = forecast_station(KLANG, NOW, NOW, observed, None, None, {1: (30.0, 40.0, 55.0)}, "model",
                               {"upwind_fire": 0.3, "rain_mm": -0.2}, row, {})
    assert payload["why"] == ["Rain on the way should help clear the air."]


class InputsStore:
    def __init__(self, cams_last):
        self.cams_last = cams_last

    def max_day(self, table):
        return self.cams_last


def test_live_daily_inputs_are_refreshed_before_forecasting(monkeypatch):
    today = date(2026, 10, 20)
    calls = []
    monkeypatch.setattr(forecast, "refresh_archive_daily", lambda store, day: calls.append(("archive", day)) or {})
    monkeypatch.setitem(forecast.BACKFILLS, "cams",
                        lambda client, store, settings, start, end: calls.append(("cams", start, end)) or {})
    forecast.refresh_daily_inputs(None, InputsStore(date(2026, 10, 15)), None, today)
    assert calls == [("archive", today), ("cams", date(2026, 10, 14), date(2026, 10, 19))]
    calls.clear()
    forecast.refresh_daily_inputs(None, InputsStore(date(2026, 10, 19)), None, today)  # already up to date
    assert calls == [("archive", today)]


class WindStore:
    def __init__(self, issued, field):
        self.stored = (issued, field)
        self.saved = None

    def wind_grid(self):
        return self.stored

    def save_wind_grid(self, issued, field):
        self.saved = (issued, field)


def test_the_wind_grid_is_fetched_only_when_the_stored_one_is_old(monkeypatch):
    fetched = []
    monkeypatch.setattr(forecast.openmeteo, "fetch_wind_grid",
                        lambda client, points, deadline=None: fetched.append(len(points)) or [])
    fresh = WindStore(NOW - timedelta(hours=1), {"times": ["x"], "u": [], "v": []})
    assert forecast.refresh_wind_grid(None, fresh, NOW) == {"times": ["x"], "u": [], "v": []}
    assert fetched == [] and fresh.saved is None
    old = WindStore(NOW - timedelta(hours=4), {"times": ["old"], "u": [], "v": []})
    field = forecast.refresh_wind_grid(None, old, NOW)
    assert fetched == [27 * 17] and old.saved == (NOW, field) and field["times"] == []


def test_a_wind_failure_never_stops_the_forecast(monkeypatch, capsys):
    def trouble(client, points, deadline=None):
        raise RuntimeError("anything at all")

    monkeypatch.setattr(forecast.openmeteo, "fetch_wind_grid", trouble)
    old = WindStore(NOW - timedelta(hours=4), {"times": ["old"], "u": [], "v": []})
    assert forecast.wind_step(None, old, NOW) == {"times": ["old"], "u": [], "v": []}
    assert "RuntimeError" in capsys.readouterr().err
