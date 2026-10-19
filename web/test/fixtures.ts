import type { Band } from "@/lib/bands";
import type { Accuracy, Day, Hour, Latest, MapData, StationDetail, StationSummary, WindData } from "@/lib/types";

// Synthetic values only: never paste real aqicn readings into the repo.
export const GENERATED = "2026-10-15T02:10:00Z"; // 10:10am MYT
const START = Date.parse("2026-10-15T02:00:00Z");

function bandFor(api: number): Band {
  return api <= 50 ? "good" : api <= 100 ? "moderate" : api <= 200 ? "unhealthy" : api <= 300 ? "very_unhealthy" : "hazardous";
}

export function makeHours(rf: (h: number) => number = (h) => 150 + (h % 12) * 5): Hour[] {
  return Array.from({ length: 48 }, (_, h) => {
    const value = rf(h);
    return {
      t: new Date(START + h * 3600_000).toISOString().replace(".000Z", "Z"), rf: value, rf_low: value - 20, rf_high: value + 30,
      band: bandFor(value), pm25: Math.round(value / 3), official_api: 160, official_low: 150, official_high: 175,
      rain_mm: h === 30 ? 3.2 : 0, wind_from: 225, wind_kmh: 8,
    };
  });
}

const BLOCKS_TOMORROW = [
  { start: "06:00", end: "12:00", status: "forecast", band: "very_unhealthy", worst_hour: "08:00", worst_rf: 230 },
  { start: "12:00", end: "18:00", status: "forecast", band: "moderate", worst_hour: "12:00", worst_rf: 95 },
  { start: "18:00", end: "00:00", status: "forecast", band: "unhealthy", worst_hour: "23:00", worst_rf: 160 },
  { start: "00:00", end: "06:00", status: "forecast", band: "unhealthy", worst_hour: "03:00", worst_rf: 150 },
] as const;

export function makeDays(): Day[] {
  return [
    { label: "today", date: "2026-10-15", best_window: null, blocks: [
      { start: "06:00", end: "12:00", status: "past", band: null, worst_hour: null, worst_rf: null },
      { start: "12:00", end: "18:00", status: "forecast", band: "unhealthy", worst_hour: "17:00", worst_rf: 180 },
      { start: "18:00", end: "00:00", status: "forecast", band: "unhealthy", worst_hour: "19:00", worst_rf: 170 },
      { start: "00:00", end: "06:00", status: "forecast", band: "unhealthy", worst_hour: "05:00", worst_rf: 165 },
    ] },
    { label: "tomorrow", date: "2026-10-16", blocks: BLOCKS_TOMORROW.map((b) => ({ ...b })),
      best_window: { start: "13:00", end: "17:00", band: "moderate" } },
    { label: "day_after", date: "2026-10-17", best_window: null, blocks: [
      { start: "06:00", end: "12:00", status: "forecast", band: "unhealthy", worst_hour: "08:00", worst_rf: 140 },
      { start: "12:00", end: "18:00", status: "forecast", band: "moderate", worst_hour: "12:00", worst_rf: 90 },
      { start: "18:00", end: "00:00", status: "unavailable", band: null, worst_hour: null, worst_rf: null },
      { start: "00:00", end: "06:00", status: "unavailable", band: null, worst_hour: null, worst_rf: null },
    ] },
  ];
}

export function makeStation(id = "ZZ01A", options: { estimated?: boolean; name?: string; state?: string } = {}): StationDetail {
  const estimated = options.estimated ?? false;
  return {
    id, name: options.name ?? "Testville", state: options.state ?? "Selangor", generated_at: GENERATED,
    estimated, method: "model",
    now: estimated
      ? { real_feel: null, real_feel_band: null, main_pollutant: null, pm25: null, real_feel_hour: null, official_api: 140,
          official_band: "unhealthy", official_hour: "2026-10-15T02:00:00Z" }
      : { real_feel: 214, real_feel_band: "very_unhealthy", main_pollutant: "pm25", pm25: 92.1,
          real_feel_hour: "2026-10-15T02:00:00Z",
          official_api: 170, official_band: "unhealthy", official_hour: "2026-10-15T02:00:00Z" },
    hours: makeHours(), days: makeDays(),
    why: ["Fires upwind, mainly in Sumatra, are adding smoke.", "Rain expected tomorrow afternoon should help clear the air."],
    closure: { school_day: "2026-10-16", probability: 0.62, rule: "three_days_above_150" },
  };
}

export function summaryOf(detail: StationDetail, lat = 3.0, lon = 101.5): StationSummary {
  return { id: detail.id, name: detail.name, state: detail.state, lat, lon, estimated: detail.estimated,
           method: detail.method, now: detail.now, next24: detail.hours.slice(0, 24).map((h) => h.band),
           closure: detail.closure };
}

export function makeLatest(): Latest {
  return { generated_at: GENERATED, stations: [
    summaryOf(makeStation("ZZ01A", { name: "Testville", state: "Selangor" }), 3.0, 101.5),
    summaryOf(makeStation("ZZ02B", { name: "Sampleton", state: "Johor", estimated: true }), 1.5, 103.7),
    summaryOf(makeStation("ZZ03C", { name: "Kampung Contoh", state: "Selangor" }), 3.2, 101.6),
  ] };
}

export function makeAccuracy(): Accuracy {
  const scores = (band: number, pod: number) => ({ n: 930, band_accuracy: band, unhealthy_days: 500, pod_unhealthy: pod,
                                                  far_unhealthy: 0.1, mae_ugm3: 8.1, coverage_80: null });
  return {
    version: "20261015T0520Z",
    backtest: {
      "1": { method: "model", meets_target: false, test_from: "2026-10-01", test_to: "2026-10-15",
             model: { ...scores(0.712, 0.81), coverage_80: 0.74 }, persistence: scores(0.58, 0.782), cams: scores(0.65, 0.796) },
      "2": { method: "cams", meets_target: false, test_from: "2026-10-01", test_to: "2026-10-15",
             model: scores(0.658, 0.758), persistence: scores(0.459, 0.687), cams: scores(0.646, 0.79) },
    },
    track_record: {},
  };
}

export function makeMap(): MapData {
  const hours = makeHours();
  return {
    generated_at: GENERATED,
    times: hours.map((h) => h.t),
    stations: [{
      id: "ZZ01A", name: "Testville", state: "Selangor", lat: 3.0, lon: 101.5, bands: hours.map((h) => h.band),
      rf: hours.map((h) => h.rf),
    }],
  };
}

export function makeWind(): WindData {
  const times = [0, 3].map((h) => new Date(START + h * 3600_000).toISOString().replace(".000Z", "Z"));
  return { generated_at: GENERATED, grid: { lon0: 100, lat0: 2, dlon: 1, dlat: 1, nx: 2, ny: 2 }, times,
           u: [[1, 1, 1, 1], [2, 2, 2, 2]], v: [[0, 0, 0, 0], [1, 1, 1, 1]] };
}
