# MYHaze — design spec

- **Date:** 2026-10-15 (Thursday)
- **Launch deadline:** before Monday 2026-10-19
- **Owner:** kiizenitc
- **Status:** awaiting owner review

## 1. Goal

A public, free website that gives Malaysian parents a **"Real Feel" of the haze for the next 48 hours** at any of the 68 DOE stations, so they can judge for themselves how to plan their children's day: school, sports, tuition, outings. It replaces the Power BI dashboard of the reference project ([herr-hollis/Malaysia-Haze-Monitor](https://github.com/herr-hollis/Malaysia-Haze-Monitor)) with a parent-friendly site in the spirit of [AirMon](https://airmon.unimas.my/), and replaces its forecast with a trained, backtested model.

The site informs; parents decide. It never tells a parent to keep a child home.

### What the owner asked for (decisions made)

| Topic | Decision |
|---|---|
| Audience | Public, all Malaysian parents. English only. |
| Headline numbers | Both: **Real Feel** (this hour's air) and **official DOE API** (24-hour average), side by side. Full 24-hour day, not just school hours. |
| Scale | Malaysian band names for both numbers. Real Feel is the overall hourly AQI on aqicn's own US AQI scale (owner decisions, 19 Oct 2026: the highest of the hour's PM2.5, PM10, O3, NO2, SO2 and CO numbers aqicn shows); the official API and closure indicator are on DOE's calibrated scale. Real Feel must never be a 24-hour average. |
| Location | Pick from the 68 DOE stations by list or map. **No GPS.** Several stations can be saved (home, school, tuition), stored only in the browser. |
| Closure indicator | Shows whether MOE's published rules *would* trigger. Clearly labelled: MOE decides, follow official MOE announcements. |
| Training data | **Malaysian air-quality data from July 2026 onward only.** Fires (Indonesia + Malaysia) and weather are inputs, not air-quality data. |
| Accuracy target | For tomorrow (D+1): **≥90% correct band AND ≥90% of Unhealthy-or-worse caught.** D+2 reported openly (aim ≥80%). Must beat simple baselines. Measured accuracy shown publicly. |
| Forecast approach | Trained hybrid model (A) with corrected-CAMS (B) as the baseline it must beat and as fallback. |
| Day plan | Four fixed 6-hour blocks (6am–12pm, 12pm–6pm, 6pm–12am, 12am–6am), each showing its worst band, plus a link to the hour-by-hour forecast. |
| Sensitive child | Optional switch, stored in the browser: advice wording turns stricter one band earlier. Forecast numbers do not change. |
| Alerts | None. Parents check the site themselves. |
| Hosting | Cloudflare (static site) + Supabase (archive) + GitHub Actions (compute). Target cost $0/month. |
| Repo / licence | Public GitHub repo under `kiizenitc`, **AGPL-3.0**. |

## 2. Definitions

- **Real Feel:** the PM2.5 concentration for *this one hour* at a station, expressed on aqicn's US AQI scale (until 19 Oct 2026: the Malaysian API scale); for the current hour it is the overall AQI, the highest of that hour's pollutant numbers aqicn shows. Only PM2.5 is forecast. It is computed by MYHaze, not an official DOE figure. It moves fast when smoke arrives.
- **Official API:** the number DOE publishes every hour. For PM2.5 it is computed from a **24-hour running average**, so it lags. This is what news, DOE and MOE use.
- **Bands** (Malaysian API): Good 0–50 · Moderate 51–100 · Unhealthy 101–200 · Very unhealthy 201–300 · Hazardous >300. Every colour is always shown with its band word.
- **Closure indicator:** the probability that MOE's published rules would be met (see §6.4). It is an indicator, not a prediction of what MOE will do.

## 3. Scope

### In v1 (by Monday)

1. Hourly data archive (DOE, aqicn, FIRMS, Open-Meteo) in Supabase, starting **immediately** — every hour not archived is hourly training data lost.
2. Trained daily model (A), hourly Real Feel shaper, official API forecast, closure indicator, plain-language "why".
3. Baseline B (corrected CAMS) and persistence, used for backtest comparison and per-station fallback.
4. Backtest report against the agreed targets.
5. Static website: Home, Station ("Plan the day" + hour by hour), Pick a station (list + map), How accurate is this?, About.
6. Public "Track record" of live accuracy, updated daily from archived forecasts.

### Not in v1

- Alerts or notifications of any kind.
- Languages other than English.
- GPS or address-level forecasts.
- Deep-learning models (revisit once a year of hourly data exists).
- School holiday calendar awareness in the closure indicator.

## 4. Data sources

| Source | What we take | Cadence | Terms and handling |
|---|---|---|---|
| **DOE MyEQMS** (`eqms.doe.gov.my/api3/publicportalapims/`: `mapcaqm`, `apitablehourly`) | Official hourly API, 68 stations | Hourly | Public data. Endpoint keeps only ~7 days, so we archive. Credit DOE. |
| **aqicn / WAQI API** (`api.waqi.info/feed/@{uid}`) | `aqi` (verified to equal DOE's official API at all 63 matched stations) and `iaqi.pm25` (hourly PM2.5 as US AQI), plus PM10, O3, NO2, SO2, CO, humidity, temperature | Hourly | Free token (in secrets). **Must email WAQI before public launch** (non-profit notice). **No redistribution of archived aqicn data**: our public site shows only the current reading, credited. Hourly history charts use our DOE archive and our own forecasts. Credit WAQI and DOE. |
| **aqicn daily history** (per-station CSV export, 1 Jul 2026 →) | Daily average PM2.5 per station: the training and backtest set | One-time, then weekly top-up by the owner if needed | Exported manually by the owner (checklist: [`docs/aqicn-export-checklist.md`](../../aqicn-export-checklist.md)). Stored only in a git-ignored folder and private Supabase Storage. Never published. |
| **aqicn API `forecast.daily`** | Not used | — | For Malaysian stations it is a flat repeat of one value (for example 252 every day). Not a usable comparison. Re-check later. |
| **NASA FIRMS** VIIRS (SNPP, NOAA-20, NOAA-21) NRT | Hotspots with FRP for 95–120°E, 6°S–8°N | Hourly pull, backfill 1 Jul 2026 → | Free MAP_KEY (owner to register). Credit NASA FIRMS. |
| **Open-Meteo forecast API** | Hourly wind 10 m / 925 hPa / 850 hPa, precipitation and probability, boundary-layer height, relative humidity, at stations and a coarse fire-region grid | Every 3 hours (source models update 2–4×/day) | Free non-commercial use, under 10,000 calls/day. Credit Open-Meteo (CC BY 4.0). |
| **Open-Meteo historical forecast / previous-runs API** | Archived *real* forecasts of the same variables at the needed lead times, for training | One-time backfill | Training features must be what was forecast at the time, never hindsight. |
| **Open-Meteo air-quality API (CAMS)** | Hourly PM2.5 forecast at stations | Every 3 hours, archived by us | Baseline B only in v1. Its "past" values are close to analysis, not true forecasts, so they are not used as a model feature for training (leakage). |

**Known gaps (accepted):** no public hourly PM2.5 history exists for July–October 2026. Hourly accuracy is proven on live data after launch. The owner has submitted aqicn's raw-data request form; if hourly data arrives, it is added in v1.1. Five DOE stations have no aqicn feed (`CA04K`, `CA11A`, `MCAQM001–003`); they get the official API plus an estimated Real Feel, labelled as estimated.

## 5. Unit conversions (verified during build, covered by unit tests)

1. aqicn `iaqi.pm25` (US AQI) → PM2.5 µg/m³ using the US EPA breakpoint table aqicn applies. Determine which EPA table (pre-2024 or 2024) by checking that the 24-hour mean of converted values reproduces DOE's official API.
2. µg/m³ → Malaysian API sub-index using DOE's PM2.5 breakpoints. The breakpoints are fitted and confirmed against DOE's own published API and aqicn's matching hourly values, then frozen in code with the evidence in `docs/methodology.md`.
3. Real Feel = step 1's US AQI table applied to a **1-hour** concentration (owner decision, 19 Oct 2026; see `docs/methodology.md`). Official API forecast = step 2 applied to the **24-hour rolling mean** of observed and forecast hourly values.

## 6. Forecast method

Every hour, for every station, produce 48 hourly values (now → +48 h) of Real Feel with a low/likely/high range, plus the official API forecast, closure indicator and "why".

### 6.1 Daily model (A, trained)

- **Algorithm:** LightGBM quantile regression (10th, 50th, 90th percentile), one model per lead (D+1, D+2), pooled across all stations. Small trees and strong regularisation for a small dataset. Monotone constraints keep physics sensible: more upwind fire never lowers the forecast, more rain never raises it.
- **Target:** daily mean PM2.5 (µg/m³) at the station, converted from aqicn's daily average US AQI. Averaging AQI values differs slightly from averaging concentrations; the effect is measured and documented in `docs/methodology.md`.
- **Issue time in training:** end of day D. Live, the model runs hourly with the latest values.
- **Features** (only information available at issue time):
  - Persistence: daily mean for D, D−1, D−2, and the 3-day trend.
  - **Upwind fire index:** Σ over hotspots of FRP × distance decay (e-folding about 500 km) × alignment between the bearing to the fire and the forecast upwind direction (925/850 hPa) for the target day.
  - Regional fire totals and 3-day trend: Riau, Jambi, South Sumatra, West/Central/South Kalimantan, Peninsular Malaysia, Sarawak, Sabah.
  - **Rain over fire regions** (forecast for D and the target day).
  - Local forecast for the target day: rain total and wet hours, mean and morning-minimum boundary-layer height, 10 m wind speed and direction, 850 hPa wind, relative humidity.
  - Station latitude, longitude and region group (Peninsular west, Peninsular east, Peninsular south, Sarawak, Sabah).
- **Explanations:** LightGBM's built-in per-feature contributions (`pred_contrib`) are mapped to plain sentences, for example "Fires upwind in South Sumatra up 40%", "Wind from the southwest", "Smoke trapped near the ground 6–9am", "Rain likely 3–6pm should help". Show the top 3–4 contributors that agree with the forecast's direction.

### 6.2 Hourly Real Feel shaper

For each hour h in the next 48:

1. **Model path:** the daily mean for that day × a diurnal factor from forecast boundary-layer height (factor ∝ BLH(h)^−k, normalised to keep the daily mean), × a washout factor for forecast rain hours.
2. **Anchor:** the live aqicn hourly reading, blended in with weight decaying from 1 to 0 with an e-folding time of about 6 hours.
3. **Range:** the daily-model quantiles carried through the same shaping.

`k` and the washout factor start from documented priors and are refitted weekly on the archived hourly data as it accumulates.

### 6.3 Official API forecast

The 24-hour rolling mean of (observed past hours + forecast hours) → DOE breakpoints → API, with a range.

### 6.4 Closure indicator

- **Rules encoded** (as reported 8 Oct 2026; stored in one config file, easy to update):
  - (a) official API **> 180** → closure;
  - (b) official API **> 150 on three consecutive days** → closure.
- **Computed for the next school day**, using each state's school week: Kedah, Kelantan and Terengganu run Sunday–Thursday, the other states Monday–Friday. Holidays are not modelled.
- Probability from the forecast range: (a) chance the daily maximum official API exceeds 180; (b) chance that day and the two before it each exceed 150, using observed values for past days.
- Shown as a percentage with the fixed caption: "Indicator only, based on MOE's published rules. MOE makes the decision. Follow official MOE announcements."

### 6.5 Baselines and fallback

- **Persistence:** tomorrow equals today.
- **B, corrected CAMS:** CAMS hourly PM2.5 × the station's error ratio over the last 7 days, per hour of day where data allows.
- The **production forecast for each station** is the best of A, B and persistence by the backtest. A is used wherever it beats both.

### 6.6 Backtest and acceptance

- **Split by time:** train 1 Jul–15 Sep 2026, tune 16–30 Sep, **test 1 Oct → latest available day** (the current haze episode). A second check holds out one region group at a time.
- **Metrics at daily level, D+1 and D+2:**
  - band accuracy;
  - detection rate (POD) of Unhealthy-or-worse;
  - false-alarm ratio;
  - MAE;
  - how often the truth falls inside the 10–90% range.
- **Pass bar:** D+1 band accuracy ≥90% **and** POD(Unhealthy+) ≥90%, **and** A beats persistence and B on both (owner decision, 19 Oct 2026: catching up to 1 point fewer unhealthy days than a baseline counts as a tie when A gets the band right more often).
- **If the bar is not met by Monday:** launch with the best-performing method, publish its true numbers on "How accurate is this?", never claim 90%, and keep training as data accrues.
- **Honest limits, stated on the site:** about 1,000 test station-days from one haze season gives roughly ±3–5 points of uncertainty. Hourly accuracy is proven only by the live Track record.
- **Every issued forecast is archived and never overwritten.** A daily verification job scores yesterday's forecasts against observations; the results feed the Track record page.

## 7. Architecture

```
             hourly · GitHub Actions (public repo, free)
 DOE ───┐
 aqicn ─┤   ┌─────────────┐   ┌──────────────┐   ┌──────────────────┐
 FIRMS ─┼──▶│ ingest +    │──▶│ forecast     │──▶│ publish JSON +   │──▶ Cloudflare ──▶ parents
 Open-  │   │ validate    │   │ A / B / pers │   │ deploy static    │    static CDN
 Meteo ─┘   └──────┬──────┘   └──────┬───────┘   └──────────────────┘
                   ▼                 ▼
         Supabase Postgres: observations, fires, weather, every forecast, verification, run log
         Supabase Storage (private): model files, backtest reports, aqicn daily CSVs
  weekly + on demand: retrain → backtest → promote the new model only if it passes and beats the current one
```

### 7.1 Repository layout (`kiizenitc/myhaze`, AGPL-3.0)

```
pipeline/            Python 3.12, managed with uv
  sources/           one module per source: doe.py, aqicn.py, firms.py, openmeteo.py
  convert.py         US AQI ↔ µg/m³ ↔ Malaysian API
  features.py        builds the feature table (training and live share one code path)
  model/             train.py, predict.py, shaper.py, closure.py, explain.py
  baselines.py       persistence, corrected CAMS
  backtest.py        splits, metrics, report
  publish.py         writes and validates site JSON
  store.py           Supabase Postgres access
  tests/             pytest, with recorded API responses as fixtures (tests never call live APIs)
web/                 Next.js (static export), TypeScript, Tailwind; MapLibre GL + OpenFreeMap tiles, lazy-loaded on the map page only
supabase/migrations/ schema
.github/workflows/   hourly.yml, train.yml, verify.yml, web.yml
docs/                this spec, methodology.md, aqicn export checklist
data/raw/            git-ignored (aqicn daily CSVs, local caches)
LICENSE              AGPL-3.0
```

### 7.2 Storage (Supabase free tier: 500 MB database, 1 GB storage)

Tables: `stations`, `obs_hourly` (station, hour, official API, PM2.5 US AQI, PM2.5 µg/m³, other pollutants, source), `fires_daily_region`, `fire_points_recent` (raw points, last 14 days), `weather_fcst` (compact per issue time), `forecasts` (one row per station per run, with the 48-hour arrays), `verification_daily`, `run_log`. Estimated growth is about 150 MB/year after compaction: forecast runs older than 90 days are reduced to the D+1/D+2 values needed for verification. Hourly writes keep the free project from pausing.

### 7.3 Schedules

| Job | When | Trigger |
|---|---|---|
| Ingest + forecast + publish | Hourly at :20 (after DOE and aqicn update) | Supabase `pg_cron` calls GitHub `workflow_dispatch` on time; GitHub's own cron at :35 is the backup (it can run 5–20 min late) |
| Weather + CAMS fetch | Every 3 hours | Inside the hourly job |
| Verification | Daily 02:00 MYT | GitHub cron |
| Retrain + backtest | Weekly, Sunday 03:00 MYT, and on demand | GitHub cron / manual |

### 7.4 Failure handling

- Each source is fetched independently with retries. A failed source keeps its last good data and is flagged stale. The forecast falls back A → B → persistence per station.
- Published JSON is schema-validated before deploy. An empty or invalid build is never published; the previous one stays live.
- The site always shows "Updated <time>". A "Data delayed" banner appears if data is over 2 hours old, and per-station notes say when a source is missing.
- Every run writes a `run_log` row (sources OK or failed, durations, model used). GitHub Actions failure emails go to the owner.

### 7.5 Secrets

`AQICN_TOKEN`, `FIRMS_MAP_KEY`, `SUPABASE_DB_URL`, `SUPABASE_SERVICE_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` live in GitHub encrypted secrets, and locally in `.env` (git-ignored). The `pg_cron` trigger uses a fine-grained GitHub token limited to running this repo's workflows, stored in Supabase Vault. Nothing secret is ever committed.

## 8. Website

### 8.1 Pages

1. **Home:** cards for saved stations. Each card: Real Feel now (big number, band word, µg/m³ small), official DOE API (24-hour average), a 24-hour colour strip, the closure indicator for the next school day, and "Updated <time>". An empty state invites "Choose your stations".
2. **Station, "Plan the day":** Today / Tomorrow / day-after tabs. Four fixed 6-hour blocks (6am–12pm, 12pm–6pm, 6pm–12am, 12am–6am), each with its worst band and when the worst hour is ("worst ~8am"). A block's band comes from the *likely* (median) hourly Real Feel; the range lives on the hourly view. "Best window outdoors" when one exists. The "why" list. Official API forecast range and closure indicator. A clear link: **"See hour-by-hour forecast"**, opening the 48-hour hourly chart (Real Feel line with shaded range, official API line, rain and wind rows).
3. **Pick a station:** all 68 stations grouped by state with search; the map shows station dots coloured by Real Feel, fire hotspots, wind arrows, and a time slider from now to +48 h.
4. **How accurate is this?:** backtest results against the targets, the live Track record (updated daily), and baselines for comparison.
5. **About:** Real Feel vs official API; which aqicn number matches which MYHaze number (aqicn's headline is DOE's 24-hour API, its PM2.5 row is Real Feel); the closure disclaimer; "not medical advice"; data credits (DOE, WAQI/aqicn, NASA FIRMS, Open-Meteo/CAMS); AGPL licence and source link.

### 8.2 Advice wording

Short, general guidance per band, adapted from DOE/MOH public API advisories, shown under the numbers. The "my child is sensitive (asthma, etc.)" switch applies the next band's wording one band early. **The owner reviews all advice text before launch.** No wording tells parents what to decide.

### 8.3 Readability rules

- Mobile first.
- Body text ≥16px; headline numbers large.
- Plain English.
- Colour always paired with the band word.
- Light and dark themes follow the phone setting.
- First load under 150 KB (the map library loads only on the map page).
- About 3 requests per page view.

## 9. Hosting and cost

| Part | Service | Cost |
|---|---|---|
| Static site + data JSON | Cloudflare (static assets, deployed from GitHub Actions with `wrangler`) | $0 |
| Archive, model files | Supabase free tier | $0 |
| Compute | GitHub Actions on a public repo | $0 |
| Map tiles | OpenFreeMap | $0 |

**Verify in the first implementation task:** that hourly `wrangler` deploys of static assets fit Cloudflare's free plan (no build-count limit applies to direct deploys, and static asset requests are not metered). If not, publish data JSON to a separate Cloudflare-served location and deploy the site only on code changes.

## 10. Licence and compliance

- Code and docs: **AGPL-3.0**. Anyone running a modified copy publicly must publish their source.
- Data stays under its sources' terms. aqicn data is not redistributed as archives; DOE, WAQI, NASA FIRMS and Open-Meteo are credited on every page footer and in About.
- The reference repo has no licence, so **none of its code or data files are copied**. MYHaze is written from scratch.
- Owner sends WAQI's required non-profit notification email before launch.

## 11. Testing

- **Unit:** conversions (known US AQI ↔ µg/m³ ↔ API pairs), feature builders (upwind fire index geometry, leakage guard that asserts no feature uses data after issue time), closure rules (consecutive-day logic, state school weeks), shaper (preserves the daily mean, anchor decay).
- **Source adapters:** tested against recorded real responses, including error and empty responses.
- **Backtest:** reproducible from a fixed snapshot; the report is committed with the model version.
- **Publish:** JSON schema validation; a smoke test that renders every page against the latest JSON.
- **Web:** component tests for the station card and day plan; a manual check on a phone-sized viewport in light and dark mode.

## 12. Timeline and risks

| Day | Work |
|---|---|
| Thu 15 | Spec ✔, implementation plan, repo + Supabase schema, **hourly archiving live today** (DOE, aqicn, FIRMS) |
| Fri 16 | Backfills (FIRMS, Open-Meteo past forecasts, Jul → now), load aqicn CSV exports, conversions verified, features, baselines |
| Sat 17 | Train A, hourly shaper, official API forecast, closure indicator, explanations, backtest report |
| Sun 18 | Website pages, Cloudflare deploy, end-to-end hourly run |
| Mon 19 | Accuracy page, advice text review, polish, WAQI email sent, **launch** |

| Risk | Mitigation |
|---|---|
| aqicn CSV exports late or incomplete | Train on the stations available; if none by Saturday, launch with B/persistence and honest accuracy, then swap A in |
| A misses the 90% bar | Launch with the best method and true numbers (§6.6) |
| DOE or aqicn feed outage | Per-source fallback and stale flags (§7.4) |
| GitHub cron delays | Supabase `pg_cron` trigger plus backup cron |
| aqicn terms | Current reading only on the site, credited; archives kept private; non-profit email before launch |
| MOE changes the rules again | Rules live in one config file |

## 13. Owner action checklist

1. Register a **NASA FIRMS MAP_KEY** (needed Friday): https://firms.modaps.eosdis.nasa.gov/api/map_key/
2. **Export the aqicn daily CSVs** for 63 stations per [`docs/aqicn-export-checklist.md`](../../aqicn-export-checklist.md) (needed by Saturday morning).
3. Create a free **Supabase project** and share the database connection string and service key (needed Thursday/Friday).
4. Create a free **Cloudflare account** and a deploy API token (needed Sunday).
5. Approve creating the **public GitHub repo** `kiizenitc/myhaze`.
6. Send WAQI the **non-profit usage notification** email (before launch).
7. Review the **advice wording** per band (Sunday).
