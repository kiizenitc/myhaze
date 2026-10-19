from datetime import date, datetime, timedelta, timezone

import pytest

from myhaze.config import MYT
from myhaze.convert import aqicn_aqi_to_ugm3, ugm3_to_real_feel
from myhaze.model.hourly import build_path, official_api_path
from myhaze.publish import (best_window, day_plan, first_trapped, latest_entry, now_block, station_payload, validate_latest,
                            validate_station, when_phrase, write_site_data)
from myhaze.rows import Station

NOW = datetime(2026, 10, 15, 15, tzinfo=timezone.utc)  # 23:00 MYT, Thursday
TIMES = [NOW + timedelta(hours=h) for h in range(48)]
KLANG = Station("CA21B", "Klang", "Selangor", 3.04, 101.45)


def sample_station():
    levels = {d: (40.0, 50.0, 70.0) for d in (date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 17))}
    path = build_path(NOW, levels, None, None)
    official = official_api_path(path, {}, 50.0)
    closure = {"school_day": "2026-10-16", "probability": 0.2, "rule": "api_above_180"}
    return station_payload(KLANG, NOW, "model", False, now_block((NOW, 60.0), (NOW, 120.0)), path, None, official,
                           closure, ["Fires upwind are adding smoke."], NOW)


def test_day_plan_blocks_follow_malaysia_time():
    today, tomorrow, after = day_plan(TIMES, list(range(48)), NOW)
    assert (today["label"], today["date"]) == ("today", "2026-10-15")
    assert [b["status"] for b in today["blocks"]] == ["past", "past", "forecast", "forecast"]
    assert today["blocks"][2]["worst_hour"] == "23:00"
    assert (today["blocks"][3]["start"], today["blocks"][3]["end"], today["blocks"][3]["worst_hour"]) == \
        ("00:00", "06:00", "05:00")
    assert [b["status"] for b in tomorrow["blocks"]] == ["forecast"] * 4
    assert [b["status"] for b in after["blocks"]] == ["forecast", "forecast", "forecast", "unavailable"]


def test_best_window_finds_the_longest_clean_stretch():
    start = datetime(2026, 10, 15, 16, tzinfo=timezone.utc)  # 00:00 MYT on the 16th
    times = [start + timedelta(hours=h) for h in range(48)]
    rf = [150] * 48
    for local_hour in (15, 16, 17, 18):
        rf[local_hour] = 80
    assert best_window(times, rf, date(2026, 10, 16)) == {"start": "15:00", "end": "19:00", "band": "moderate"}
    assert best_window(times, [150] * 48, date(2026, 10, 16)) is None


def test_when_phrase_reads_naturally():
    now = datetime(2026, 10, 15, 2, tzinfo=timezone.utc)  # Thu 10:00 MYT

    def at(day, hour):
        return datetime(2026, 10, day, hour, tzinfo=MYT)

    assert [when_phrase(at(15, 15), now), when_phrase(at(15, 20), now), when_phrase(at(16, 3), now),
            when_phrase(at(16, 8), now), when_phrase(at(17, 14), now)] == \
        ["this afternoon", "tonight", "overnight", "tomorrow morning", "on Saturday afternoon"]


def test_station_payload_matches_the_contract():
    payload = sample_station()
    validate_station(payload)
    assert payload["now"] == {"real_feel": payload["now"]["real_feel"], "real_feel_band": payload["now"]["real_feel_band"],
                              "main_pollutant": "pm25", "pm25": 60.0, "real_feel_hour": "2026-10-15T15:00:00Z",
                              "official_api": 120,
                              "official_band": "unhealthy", "official_hour": "2026-10-15T15:00:00Z"}
    entry = latest_entry(payload, KLANG)
    assert len(entry["next24"]) == 24 and entry["lat"] == 3.04
    validate_latest({"generated_at": "x", "stations": [entry]})


def test_invalid_data_is_never_written(tmp_path):
    good = sample_station()
    broken = dict(good, hours=good["hours"][:10])
    with pytest.raises(ValueError):
        validate_station(broken)
    with pytest.raises(ValueError):
        validate_latest({"stations": []})
    with pytest.raises(ValueError):
        write_site_data(tmp_path / "out", {"generated_at": "x", "stations": [latest_entry(good, KLANG)]}, [good, broken], {})
    assert not (tmp_path / "out").exists()


def test_nan_never_reaches_the_published_json(tmp_path):
    good = sample_station()
    good["hours"][0]["rain_mm"] = float("nan")
    with pytest.raises(ValueError):
        write_site_data(tmp_path / "out", {"generated_at": "x", "stations": [latest_entry(good, KLANG)]}, [good], {})
    assert not (tmp_path / "out" / "latest.json").exists()


def test_real_feel_now_is_the_pm25_number_aqicn_shows():
    block = now_block((NOW, aqicn_aqi_to_ugm3(130)), (NOW, 155.0))
    assert (block["real_feel"], block["real_feel_band"]) == (130, "unhealthy")
    assert (block["official_api"], block["official_band"]) == (155, "unhealthy")


def test_real_feel_now_is_the_highest_of_the_hours_pollutants():
    block = now_block((NOW, aqicn_aqi_to_ugm3(40)), (NOW, 60.0), {"o3": 72.0, "pm10": 30.0})
    assert (block["real_feel"], block["real_feel_band"], block["main_pollutant"]) == (72, "moderate", "o3")
    assert block["pm25"] == round(aqicn_aqi_to_ugm3(40), 1)


def test_pm25_is_named_when_it_leads():
    block = now_block((NOW, aqicn_aqi_to_ugm3(130)), (NOW, 155.0), {"pm10": 60.0})
    assert (block["real_feel"], block["main_pollutant"]) == (130, "pm25")


def test_no_reading_names_no_pollutant():
    assert now_block(None, (NOW, 155.0), {"o3": 20.0})["main_pollutant"] is None


def test_forecast_hours_show_real_feel_on_aqicns_scale():
    for hour in sample_station()["hours"]:
        assert abs(hour["rf"] - ugm3_to_real_feel(hour["pm25"])) <= 1


def test_trapped_smoke_is_mentioned_only_when_there_is_haze_to_trap():
    from myhaze.model.hourly import HourlyPath

    morning = datetime(2026, 10, 15, 22, tzinfo=timezone.utc)  # 06:00 MYT
    times = [morning - timedelta(hours=1), morning]
    clean = HourlyPath(times, [3.0, 3.0], [5.0, 5.0], [8.0, 8.0], [True, True])
    hazy = HourlyPath(times, [40.0, 40.0], [60.0, 60.0], [90.0, 90.0], [True, True])
    assert first_trapped(clean) is None
    assert first_trapped(hazy) == morning

def test_map_payload_carries_each_stations_48_hourly_bands_and_real_feel():
    from myhaze.publish import map_payload

    good = sample_station()
    got = map_payload([good], {"CA21B": KLANG}, NOW)
    assert got["times"] == [h["t"] for h in good["hours"]]
    entry = got["stations"][0]
    # Wind lives in wind.json now (a flowing field), so stations carry no wind of their own.
    assert entry == {"id": "CA21B", "name": "Klang", "state": "Selangor", "lat": 3.04, "lon": 101.45,
                     "bands": [h["band"] for h in good["hours"]], "rf": [h["rf"] for h in good["hours"]]}


def test_map_payload_says_which_hours_the_now_readings_are_from():
    from myhaze.publish import map_payload

    fresh, late, none = sample_station(), sample_station(), sample_station()
    late["now"] = {**late["now"], "real_feel_hour": "2026-10-15T14:00:00Z"}  # this station's feed is an hour behind
    none["now"] = {**none["now"], "real_feel_hour": None}
    got = map_payload([fresh, late, none], {"CA21B": KLANG}, NOW)
    assert got["readings"] == ["2026-10-15T14:00:00Z", "2026-10-15T15:00:00Z"]
    assert map_payload([none], {"CA21B": KLANG}, NOW)["readings"] is None
