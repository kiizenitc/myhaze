# MYHaze

A free website that gives Malaysian parents a 48-hour "Real Feel" of the haze at every DOE air-quality station, so they can plan their children's day.

**Status:** being built. The hourly data archive runs first; the forecast and website follow.

## How it works so far

Every 15 minutes a GitHub Actions job archives these into a private Supabase database:

- DOE's official Air Pollutant Index for every station. DOE's public feed only keeps about 7 days.
- aqicn's hourly readings from DOE's monitors.
- CAMS PM2.5 forecasts from Open-Meteo, every 6 hours.

Design: [docs/superpowers/specs/2026-10-15-myhaze-design.md](docs/superpowers/specs/2026-10-15-myhaze-design.md)

## Run locally

```bash
brew install uv
cp .env.example .env   # then fill in AQICN_TOKEN and SUPABASE_DB_URL
uv --directory pipeline run pytest
uv --directory pipeline run python -m myhaze.migrate
uv --directory pipeline run python -m myhaze.jobs.archive
```

## Data credits

- Department of Environment Malaysia (DOE), MyEQMS / APIMS
- World Air Quality Index Project ([aqicn.org](https://aqicn.org)), relaying DOE data
- [Open-Meteo](https://open-meteo.com) (CC BY 4.0), with CAMS air-quality forecasts from Copernicus/ECMWF

Archived aqicn data is never redistributed, as aqicn's terms require.

## Licence

AGPL-3.0. See [LICENSE](LICENSE).
