-- FIRMS fire radiative power per 0.25° cell per UTC day. Private like every other table.
create table fire_grid_daily (
  day date not null,
  lat_bin real not null,
  lon_bin real not null,
  frp_sum real not null,
  detections integer not null,
  primary key (day, lat_bin, lon_bin)
);
alter table fire_grid_daily enable row level security;
