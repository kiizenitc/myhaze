# How MYHaze turns readings into numbers

## Two scales

- **Real Feel** is one hour's PM2.5 at a station on aqicn's own US AQI scale (the US EPA 2012 table). It is the
  same number aqicn.org shows in a station's PM2.5 row for that hour. The map, the 48-hour forecast, the day plan,
  the backtest and the live track record all use it.
- **The official API** is DOE's 24-hour average on DOE's own PM2.5 table. MYHaze's official API forecast and the
  MOE closure indicator use it, so they follow DOE's numbers.

Both numbers use Malaysia's band names: 0–50 Good, 51–100 Moderate, 101–200 Unhealthy, 201–300 Very unhealthy,
above 300 Hazardous.

The owner chose this split on 19 Oct 2026. Before that, MYHaze guessed DOE's table from the 2020 Malaysian Ambient
Air Quality Standard, decoded aqicn with the 2024 US table, and put Real Feel on the same guessed table.

## Calibration (19 Oct 2026)

DOE does not publish its PM2.5 breakpoints online. `python -m myhaze.jobs.calibrate` finds them from the archive:
it turns each hour's aqicn PM2.5 into µg/m³ with a candidate US table, takes the 24-hour mean, applies a candidate
DOE table, and compares the result with DOE's own published API for hours where PM2.5 is the dominant pollutant.

Run on 4,801 station-hours (15–19 Oct 2026), mean absolute error against DOE's published API:

| aqicn table | DOE table | Error (API points) |
|---|---|---|
| **US EPA 2012** | **modified EPA** | **0.96** |
| US EPA 2024 | modified EPA | 3.82 |
| US EPA 2024 | US EPA 2024 | 8.01 |
| US EPA 2012 | US EPA 2012 | 8.18 |
| US EPA 2024 | MAAQS 2020 (the earlier guess) | 16.02 |
| US EPA 2012 | MAAQS 2020 | 19.15 |

By DOE API range, for the chosen pair:

| DOE API | Station-hours | Mean error | Within 3 points |
|---|---|---|---|
| 0–49 | 81 | +0.3 | 100% |
| 50–99 | 2,857 | −0.3 | 97% |
| 100–149 | 133 | −1.8 | 49% |
| 150–199 | 1,715 | −0.1 | 96% |
| 200–249 | 15 | +2.0 | 80% |

The 100–149 range is loosest because DOE's table fits API 101–150 into 50.5–55.4 µg/m³, so a small difference in
concentration moves the API a lot. The earlier guess read about 24 points too high whenever DOE was in 150–199.

The fit also confirms that DOE's PM2.5 API is the 24-hour mean of the same hourly readings aqicn relays, and that
aqicn's PM2.5 row is the raw hourly reading, not an average.

## Why Real Feel is not on DOE's table

DOE's table calls up to about 50 µg/m³ Moderate, then climbs from 99 to about 146 by 55 µg/m³. On an hourly
number, that hides 35–50 µg/m³ air and makes small changes near 50–55 µg/m³ look like big ones. aqicn's US AQI
scale rises evenly, follows health guidance, and lets parents check MYHaze against aqicn directly.
