import type { Band } from "./bands";

export type { Band };

export type Pollutant = "pm25" | "pm10" | "o3" | "no2" | "so2" | "co";

export interface Now {
  real_feel: number | null;
  real_feel_band: Band | null;
  main_pollutant?: Pollutant | null; // the pollutant with the highest US AQI number this hour
  pm25: number | null;
  real_feel_hour: string | null;
  official_api: number | null;
  official_band: Band | null;
  official_hour: string | null;
}

export interface Closure {
  school_day: string;
  probability: number | null;
  rule: "api_above_180" | "three_days_above_150" | null;
}

export interface StationSummary {
  id: string;
  name: string;
  state: string;
  lat: number;
  lon: number;
  estimated: boolean;
  method: string;
  now: Now;
  next24: Band[];
  closure: Closure;
}

export interface Latest {
  generated_at: string;
  stations: StationSummary[];
}

export interface Hour {
  t: string;
  rf: number;
  rf_low: number;
  rf_high: number;
  band: Band;
  pm25: number;
  official_api: number | null;
  official_low: number | null;
  official_high: number | null;
  rain_mm: number | null;
  wind_from: number | null;
  wind_kmh: number | null;
}

export interface Block {
  start: string;
  end: string;
  status: "forecast" | "past" | "unavailable";
  band: Band | null;
  worst_hour: string | null;
  worst_rf: number | null;
}

export interface Day {
  label: "today" | "tomorrow" | "day_after";
  date: string;
  blocks: Block[];
  best_window: { start: string; end: string; band: Band } | null;
}

export interface StationDetail {
  id: string;
  name: string;
  state: string;
  generated_at: string;
  estimated: boolean;
  method: string;
  now: Now;
  hours: Hour[];
  days: Day[];
  why: string[];
  closure: Closure;
}

export interface Fires {
  generated_at: string;
  cells: [number, number, number][];
}

export interface MethodScores {
  n: number;
  band_accuracy: number | null;
  unhealthy_days: number;
  pod_unhealthy: number | null;
  far_unhealthy: number | null;
  mae_ugm3: number | null;
  coverage_80: number | null;
}

export interface LeadReport {
  method: string;
  meets_target: boolean;
  test_from: string;
  test_to: string;
  model: MethodScores;
  persistence: MethodScores;
  cams: MethodScores;
}

export interface TrackRecord {
  days: number;
  hours: number;
  band_accuracy: number | null;
  unhealthy_hours: number;
  pod_unhealthy: number | null;
}

export interface Accuracy {
  version: string | null;
  backtest: Record<string, LeadReport> | null;
  track_record: Record<string, TrackRecord>;
}

export interface MapStation {
  id: string;
  name: string;
  state: string;
  lat: number;
  lon: number;
  bands: Band[];
  rf: number[];
}

export interface MapData {
  generated_at: string;
  times: string[];
  readings?: [string, string] | null; // oldest and newest hour of the stations' latest readings
  stations: MapStation[];
}

export interface WindGrid {
  lon0: number;
  lat0: number;
  dlon: number;
  dlat: number;
  nx: number;
  ny: number;
}

/** wind.json: 3-hourly frames of the wind ~120 m up, m/s east (u) and north (v), grid rows from the south. */
export interface WindData {
  generated_at: string;
  grid: WindGrid;
  times: string[];
  u: (number | null)[][];
  v: (number | null)[][];
}
