-- The latest gridded wind forecast for the map (refreshed every 3 hours; one row per name, 'latest' in production).
create table wind_grid (
  name text primary key,
  issued_at timestamptz not null,
  field jsonb not null
);

alter table wind_grid enable row level security;
