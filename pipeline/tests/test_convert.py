import pytest

from myhaze import convert
from myhaze.convert import MY_TABLES, US_TABLES, band, conc_from_index, index_from_conc


@pytest.mark.parametrize("api,expected", [(0, "good"), (50, "good"), (51, "moderate"), (100, "moderate"),
                                          (101, "unhealthy"), (200, "unhealthy"), (201, "very_unhealthy"),
                                          (300, "very_unhealthy"), (301, "hazardous"), (999, "hazardous")])
def test_band_edges(api, expected):
    assert band(api) == expected


def test_band_rounds_before_comparing():
    assert band(100.4) == "moderate" and band(100.6) == "unhealthy"


@pytest.mark.parametrize("table,conc,index", [
    ("us_epa_2024", 9.0, 50), ("us_epa_2024", 35.4, 100), ("us_epa_2024", 55.5, 151), ("us_epa_2024", 125.4, 200),
    ("us_epa_2012", 12.0, 50), ("us_epa_2012", 150.4, 200),
])
def test_us_tables(table, conc, index):
    assert index_from_conc(conc, US_TABLES[table]) == pytest.approx(index, abs=0.01)


def test_my_maaqs_table_points():
    table = MY_TABLES["maaqs2020"]
    assert index_from_conc(15, table) == pytest.approx(50)
    assert index_from_conc(35, table) == pytest.approx(100)
    assert index_from_conc(75, table) == pytest.approx(200)


@pytest.mark.parametrize("name", sorted(MY_TABLES))
def test_round_trip_and_edges(name):
    table = MY_TABLES[name]
    for conc in (0.0, 5.0, 40.0, 140.0, 400.0):
        assert conc_from_index(index_from_conc(conc, table), table) == pytest.approx(conc, abs=1e-6)
    assert index_from_conc(-3, table) == 0
    assert index_from_conc(900, table) > 500  # extrapolates above the table, never crashes


def test_load_calibration_defaults_when_file_missing(tmp_path):
    assert convert.load_calibration(tmp_path / "missing.json") == {"aqicn_table": "us_epa_2024", "my_table": "maaqs2020"}


def test_load_calibration_ignores_unknown_table_names(tmp_path):
    path = tmp_path / "cal.json"
    path.write_text('{"aqicn_table": "nope", "my_table": "modified_epa"}')
    assert convert.load_calibration(path) == {"aqicn_table": "us_epa_2024", "my_table": "modified_epa"}
