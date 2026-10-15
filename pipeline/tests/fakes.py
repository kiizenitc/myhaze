"""In-memory stand-in for myhaze.store.Store with the same method names and return types."""


class FakeStore:
    def __init__(self, stations=None, aqicn=None):
        self._stations = {s.station_id: s for s in (stations or [])}
        self._aqicn = dict(aqicn or {})
        self.obs = {}
        self.cams = {}
        self.runs = []
        self.fire_cells_store = {}

    def upsert_stations(self, stations, aqicn=None):
        for station in stations:
            self._stations[station.station_id] = station
        if aqicn is not None:
            for station in stations:
                self._aqicn.pop(station.station_id, None)
            self._aqicn.update({station_id: uid for station_id, (uid, _km) in aqicn.items()})
        return len(stations)

    def stations(self):
        return sorted(self._stations.values(), key=lambda s: s.station_id)

    def aqicn_uids(self):
        return dict(self._aqicn)

    def upsert_obs(self, rows):
        keep = [r for r in rows if r.station_id in self._stations]
        for r in keep:
            self.obs[(r.station_id, r.hour, r.source)] = r
        return len(keep), len(rows) - len(keep)

    def latest_hours(self, source):
        latest = {}
        for station_id, hour, src in self.obs:
            if src == source and (station_id not in latest or hour > latest[station_id]):
                latest[station_id] = hour
        return latest

    def count_obs_at(self, source, hour):
        return sum(1 for (_, h, src) in self.obs if src == source and h == hour)

    def cams_slot_done(self, slot):
        return any(issued == slot for (_, issued) in self.cams)

    def upsert_cams(self, rows):
        keep = [r for r in rows if r.station_id in self._stations]
        for r in keep:
            self.cams[(r.station_id, r.issued_slot)] = r
        return len(keep)

    def log_run(self, job, started_at, finished_at, status, details):
        self.runs.append((job, status, details))

    def upsert_fire_cells(self, cells):
        for c in cells:
            self.fire_cells_store[(c.day, c.lat_bin, c.lon_bin)] = c
        return len(cells)

    def fire_cells(self, start, end):
        return sorted((c for c in self.fire_cells_store.values() if start <= c.day <= end),
                      key=lambda c: (c.day, c.lat_bin, c.lon_bin))

    def daily_pm25(self, start, end):
        return {}

    def weather_daily(self, start, end):
        return {}

    def cams_daily(self, start, end):
        return {}
