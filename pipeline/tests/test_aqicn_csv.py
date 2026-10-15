from datetime import date

import pytest

from myhaze.sources.aqicn_csv import parse_daily_csv

EXPORT = (
    "date, pm25, pm10, o3, no2, so2, co\n"
    "2026/10/14, 172, 52, 3, 8, 2, 1\n"
    "2026/7/1, 61, 30, , 5, 1, \n"
    "2026-09-30, , 40, 2, 4, 1, 1\n"
    "garbage, 10\n"
    "2026/10/13,  159 , 48, 3, 7, 2, 1\n"
)


def test_parse_daily_csv_handles_spaces_dates_and_blanks():
    assert parse_daily_csv(EXPORT) == [(date(2026, 7, 1), 61.0), (date(2026, 10, 13), 159.0),
                                       (date(2026, 10, 14), 172.0)]


def test_parse_daily_csv_requires_the_pm25_column():
    with pytest.raises(ValueError):
        parse_daily_csv("date, pm10\n2026/10/14, 52\n")


def test_parse_daily_csv_of_empty_text_is_empty():
    assert parse_daily_csv("") == []
