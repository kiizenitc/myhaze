-- Daily summaries of archived real forecasts (lead 1 = issued the day before, lead 2 = two days before),
-- the latest hourly forecast per point, and CAMS daily means for the corrected-CAMS baseline.
-- weather tables also hold fire-region rain points ('R:...'), so they have no station foreign key.
create table weather_daily (
  station_id text not null,
  day date not null,
  lead_days smallint not null check (lead_days between 1 and 2),
  precip_mm real,
  wet_hours smallint,
  wind10_kmh real,
  wind120_kmh real,
  wind120_from_deg real,
  rh_mean real,
  primary key (station_id, day, lead_days)
);

create table weather_latest (
  station_id text primary key,
  issued_at timestamptz not null,
  times timestamptz[] not null,
  precip real[] not null,
  blh real[] not null,
  wind10 real[] not null,
  wind120 real[] not null,
  wind120_from real[] not null,
  rh real[] not null
);

create table cams_daily (
  station_id text not null references stations (station_id),
  day date not null,
  pm25_ugm3 real not null,
  primary key (station_id, day)
);

alter table weather_daily enable row level security;
alter table weather_latest enable row level security;
alter table cams_daily enable row level security;
