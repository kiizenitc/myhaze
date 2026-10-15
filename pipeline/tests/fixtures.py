"""Small payloads shaped exactly like real API responses (October 2026), trimmed to a few stations."""

DOE_STATIONS = {"data": [
    {"ID": 1, "STATE_ID": 9, "STATE_NAME": "Perlis", "STATION_STATUS": 1, "STATION_ID": "CA01R",
     "STATION_LOCATION": "Kangar, PERLIS", "LONGITUDE": 100.210937, "LATITUDE": 6.429928,
     "API": 56, "PARAM_SYMBOL": "**", "CLASS": "Moderate", "RECORD_DT": "2026-10-15T07:00:00"},
    {"ID": 66, "STATE_ID": 10, "STATE_NAME": "Selangor", "STATION_STATUS": 1, "STATION_ID": "MCAQM001",
     "STATION_LOCATION": "JOHAN SETIA", "LONGITUDE": 101.47, "LATITUDE": 2.98,
     "API": 160, "PARAM_SYMBOL": "**", "CLASS": "Unhealthy", "RECORD_DT": "2026-10-15T07:00:00"},
    {"ID": 99, "STATION_ID": "CA98X", "STATION_LOCATION": "Broken, NOWHERE",
     "LATITUDE": None, "LONGITUDE": None},
]}

DOE_STATELIST = [
    {"STATE_ID": 9, "STATE_NAME": "Perlis"},
    {"STATE_ID": 10, "STATE_NAME": "Selangor"},
]

DOE_HOURLY = {"api_table_hourly": [
    {"STATION_ID": "CA01R", "STATE_ID": 9, "STATION_LOCATION": "Kangar, PERLIS",
     "DATETIME": "2026-10-15T00:00:00", "API": 57, "PARAM_SYMBOL": "**"},
    {"STATION_ID": "CA01R", "STATE_ID": 9, "DATETIME": "2026-10-15T01:00:00", "API": None, "PARAM_SYMBOL": None},
    {"STATION_ID": "CA01R", "STATE_ID": 9, "DATETIME": "2026-10-15T02:00:00", "API": -1, "PARAM_SYMBOL": ""},
    {"STATION_ID": "CA01R", "STATE_ID": 9, "DATETIME": "2026-10-15T03:00:00", "API": "62", "PARAM_SYMBOL": "**"},
]}

DOE_HOURLY_NOW = {"api_table_hourly": [
    {"STATION_ID": "CA01R", "STATE_ID": 9, "DATETIME": "2026-10-15T08:00:00", "API": 56, "PARAM_SYMBOL": "**"},
    {"STATION_ID": "MCAQM001", "STATE_ID": 10, "DATETIME": "2026-10-15T08:00:00", "API": 160, "PARAM_SYMBOL": "**"},
    {"STATION_ID": "CA99X", "STATE_ID": 10, "DATETIME": "2026-10-15T08:00:00", "API": 90, "PARAM_SYMBOL": "**"},
]}

AQICN_BOUNDS = {"status": "ok", "data": [
    {"lat": 6.429928, "lon": 100.210937, "uid": 3001, "aqi": "56",
     "station": {"name": "Kangar, Perlis, Malaysia", "time": "2026-10-15T09:00:00+09:00"}},
    {"lat": 1.3521, "lon": 103.8198, "uid": 5555, "aqi": "80",
     "station": {"name": "Central, Singapore", "time": "2026-10-15T09:00:00+09:00"}},
    {"lat": 4.5841, "lon": 101.0829, "uid": 4004, "aqi": "120",
     "station": {"name": "Ipoh, Perak, Malaysia", "time": "2026-10-15T09:00:00+09:00"}},
]}

AQICN_FEED_KANGAR = {"status": "ok", "data": {
    "idx": 3001, "aqi": 56, "dominentpol": "",
    "time": {"s": "2026-10-15 08:00:00", "tz": "+08:00", "v": 1792051200, "iso": "2026-10-15T08:00:00+08:00"},
    "city": {"name": "Kangar, Perlis, Malaysia", "geo": [6.429928, 100.210937]},
    "iaqi": {"co": {"v": 0.1}, "h": {"v": 94}, "no2": {"v": 8}, "o3": {"v": 2.3}, "p": {"v": 1011},
             "pm10": {"v": 52}, "pm25": {"v": 130}, "so2": {"v": 1.7}, "t": {"v": 25}, "w": {"v": 1}},
    "forecast": {"daily": {}},
}}

AQICN_FEED_OFFLINE = {"status": "ok", "data": {
    "idx": 4004, "aqi": "-", "time": {"iso": "2026-10-15T08:00:00+08:00"}, "iaqi": {}}}

AQICN_FEED_ERROR = {"status": "error", "data": "Unknown station"}

CAMS_TWO_STATIONS = [
    {"latitude": 6.4, "longitude": 100.2, "hourly_units": {"time": "iso8601", "pm2_5": "μg/m³"},
     "hourly": {"time": ["2026-10-15T00:00", "2026-10-15T01:00", "2026-10-15T02:00"],
                "pm2_5": [20.1, None, 22.5]}},
    {"latitude": 3.0, "longitude": 101.5, "hourly_units": {"time": "iso8601", "pm2_5": "μg/m³"},
     "hourly": {"time": ["2026-10-15T00:00", "2026-10-15T01:00", "2026-10-15T02:00"],
                "pm2_5": [61.0, 64.2, 70.9]}},
]
