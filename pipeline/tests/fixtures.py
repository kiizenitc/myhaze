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
