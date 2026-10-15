from datetime import date, timedelta

from myhaze.jobs.backfill import HISTORY_START
from myhaze.jobs.train import collect_rows
from myhaze.rows import FireCell, Station
from tests.fakes import FakeStore

KUANTAN = Station("CA30C", "Balok Baru, Kuantan", "Pahang", 3.96, 103.38)


def test_training_never_sees_gas_flares():
    today = date(2026, 9, 1)
    store = FakeStore(stations=[KUANTAN])
    days = [HISTORY_START - timedelta(days=4) + timedelta(days=k) for k in range((today - HISTORY_START).days + 5)]
    store.upsert_fire_cells([FireCell(d, 4.5, 103.25, 20.0, 1) for d in days])  # the Kerteh flare, every day
    store.upsert_fire_cells([FireCell(days[40], 3.5, 102.75, 80.0, 4)])  # one real burn in Pahang
    rows, _cams, _pm = collect_rows(store, today)
    burning = {r.issue_day - timedelta(days=1) for r in rows if r.x["fire_peninsular"] > 0}
    assert burning == {days[40]}
