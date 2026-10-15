-- Trained model versions (report and the method shipped per lead) and their LightGBM boosters as text.
create table model_versions (
  version text primary key,
  created_at timestamptz not null default now(),
  methods jsonb not null,
  report jsonb not null
);

create table model_boosters (
  version text not null references model_versions (version) on delete cascade,
  lead_days smallint not null,
  quantile double precision not null,
  booster text not null,
  primary key (version, lead_days, quantile)
);

alter table model_versions enable row level security;
alter table model_boosters enable row level security;
