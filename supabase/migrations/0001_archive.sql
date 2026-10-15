-- MYHaze archive schema. Raw source values only; unit conversions happen in the forecast pipeline.
-- Row level security is on for every table and there are no policies: only the pipeline's direct
-- (table-owner) connection can read or write. aqicn's terms forbid redistributing archived data.

create table stations (
  station_id text primary key,
  name text not null,
  state text not null,
  lat double precision not null,
  lon double precision not null,
  aqicn_uid integer,
  aqicn_km real,
  active boolean not null default true,
  updated_at timestamptz not null default now()
);

create table obs_hourly (
  station_id text not null references stations (station_id),
  hour timestamptz not null,
  source text not null check (source in ('doe', 'aqicn')),
  api smallint,
  param_symbol text,
  pm25_aqi smallint,
  pm10_aqi smallint,
  o3_aqi real,
  no2_aqi real,
  so2_aqi real,
  co_aqi real,
  temp_c real,
  rh real,
  wind real,
  pressure real,
  fetched_at timestamptz not null default now(),
  primary key (station_id, hour, source)
);
create index obs_hourly_source_hour on obs_hourly (source, hour);

create table cams_fcst (
  station_id text not null references stations (station_id),
  issued_slot timestamptz not null,
  first_valid timestamptz not null,
  pm25 real[] not null,
  primary key (station_id, issued_slot)
);
create index cams_fcst_slot on cams_fcst (issued_slot);

create table run_log (
  id bigserial primary key,
  job text not null,
  started_at timestamptz not null,
  finished_at timestamptz not null,
  status text not null check (status in ('ok', 'partial', 'failed')),
  details jsonb not null
);

alter table stations enable row level security;
alter table obs_hourly enable row level security;
alter table cams_fcst enable row level security;
alter table run_log enable row level security;
