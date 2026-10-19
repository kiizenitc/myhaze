from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pytest

from myhaze.jobs.verify import score_runs


def test_score_runs_compares_forecast_bands_with_what_happened():
    first = datetime(2026, 10, 15, 0, tzinfo=timezone.utc)
    runs = [(first, "S", first, [20.0] * 48)]  # moderate everywhere; hour 0 is the live anchor, not scored
    observed = {"S": {first + timedelta(hours=h): (20.0 if h < 30 else 200.0) for h in range(48)}}
    totals = defaultdict(lambda: [0, 0, 0, 0])
    for _day, horizon, hours, hits, bad, caught in score_runs(runs, observed):
        for i, v in enumerate((hours, hits, bad, caught)):
            totals[horizon][i] += v
    assert totals["1-24h"] == [24, 24, 0, 0]
    assert totals["25-48h"] == [23, 5, 18, 0]


def test_only_a_completed_day_is_scored():
    from datetime import date

    first = datetime(2026, 10, 15, 0, tzinfo=timezone.utc)
    runs = [(first, "S", first, [20.0] * 48)]
    observed = {"S": {first + timedelta(hours=h): 20.0 for h in range(48)}}
    rows = score_runs(runs, observed, only_day=date(2026, 10, 15))
    assert {row[0] for row in rows} == {date(2026, 10, 15)}


def test_hours_are_scored_on_the_real_feel_scale():
    first = datetime(2026, 10, 15, 0, tzinfo=timezone.utc)
    runs = [(first, "S", first, [42.0] * 48)]  # Real Feel 117: unhealthy, though DOE's own table calls it moderate
    observed = {"S": {first + timedelta(hours=h): 42.0 for h in range(48)}}
    rows = score_runs(runs, observed)
    assert (sum(r[4] for r in rows), sum(r[5] for r in rows)) == (47, 47)


@pytest.mark.parametrize("job", ["verify", "train"])
def test_a_failed_database_connect_never_prints_the_password(job, monkeypatch, capsys):
    import importlib

    from myhaze.config import Settings
    from myhaze.store import Store

    module = importlib.import_module(f"myhaze.jobs.{job}")
    url = "postgresql://user:HUNTER2SECRET@db.example:5432/postgres"
    monkeypatch.setattr(module, "load_settings", lambda: Settings(aqicn_token="t", db_url=url))

    def refuse(cls, db_url):
        raise RuntimeError(f"connection to {db_url} failed")

    monkeypatch.setattr(Store, "connect", classmethod(refuse))
    assert module.main([]) == 1
    captured = capsys.readouterr()
    assert "HUNTER2SECRET" not in captured.out + captured.err
