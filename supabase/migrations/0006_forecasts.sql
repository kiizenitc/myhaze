-- Forecast runs archived every 6 hours (hourly median PM2.5 and official API), and daily verification scores.
create table forecast_runs (
  run_at timestamptz not null,
  station_id text not null references stations (station_id),
  method text not null,
  first_valid timestamptz not null,
  pm25 real[] not null,
  official_api real[] not null,
  primary key (run_at, station_id)
);

create table verification_daily (
  day date not null,
  horizon text not null check (horizon in ('1-24h', '25-48h')),
  hours integer not null,
  band_hits integer not null,
  bad_hours integer not null,
  bad_caught integer not null,
  primary key (day, horizon)
);

alter table forecast_runs enable row level security;
alter table verification_daily enable row level security;
