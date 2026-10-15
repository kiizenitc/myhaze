from collections import defaultdict
from datetime import datetime, timedelta, timezone

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
