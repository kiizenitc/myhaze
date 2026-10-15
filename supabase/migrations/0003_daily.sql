-- Daily-mean PM2.5 (µg/m³) per station and Malaysia calendar day: the training target and persistence input.
-- 'aqicn_csv' rows come from the owner's one-time exports; 'archive' rows from our own hourly archive.
create table daily_pm25 (
  station_id text not null references stations (station_id),
  day date not null,
  pm25_ugm3 real not null,
  source text not null check (source in ('aqicn_csv', 'archive')),
  primary key (station_id, day, source)
);
alter table daily_pm25 enable row level security;
