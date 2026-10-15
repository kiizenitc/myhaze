import math
from datetime import datetime, timedelta, timezone

import pytest

from myhaze.calibration import calibrate
from myhaze.convert import MY_TABLES, US_TABLES, index_from_conc

START = datetime(2026, 10, 15, tzinfo=timezone.utc)


def synthetic(hours=96, stations=4, us="us_epa_2024", my="maaqs2020"):
    aqicn, doe = {}, {}
    for s in range(stations):
        # 24-hour means span ~35–105 µg/m³, covering the range where the candidate tables disagree
        conc = {START + timedelta(hours=h): 10 + 60 * (1 + math.sin(h / 7 + s)) for h in range(hours)}
        aqicn[f"S{s}"] = {t: round(index_from_conc(c, US_TABLES[us])) for t, c in conc.items()}
        doe[f"S{s}"] = {}
        for h in range(23, hours):
            t = START + timedelta(hours=h)
            mean24 = sum(conc[t - timedelta(hours=k)] for k in range(24)) / 24
            doe[f"S{s}"][t] = round(index_from_conc(mean24, MY_TABLES[my]))
    return aqicn, doe


@pytest.mark.parametrize("us,my", [("us_epa_2024", "maaqs2020"), ("us_epa_2012", "modified_epa")])
def test_calibrate_recovers_the_tables_that_generated_the_data(us, my):
    aqicn, doe = synthetic(us=us, my=my)
    result = calibrate(aqicn, doe)
    assert (result["aqicn_table"], result["my_table"]) == (us, my)
    assert result["mae"] < 2.0 and result["n"] >= 200


def test_calibrate_refuses_too_little_data():
    aqicn, doe = synthetic(hours=30, stations=1)
    with pytest.raises(ValueError):
        calibrate(aqicn, doe)
