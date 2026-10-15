import type { WindData, WindGrid } from "./types";

export interface Field {
  u: (number | null)[];
  v: (number | null)[];
}

const METRES_PER_DEGREE = 111_320;
const EARTH_CIRCUMFERENCE_M = 40_075_016;
const TILE = 512; // MapLibre's world is 512 px wide at zoom 0

/** The wind at `time`, interpolated between the 3-hourly frames around it and held beyond the first and last. */
export function fieldAt(wind: WindData, time: string): Field | null {
  const t = Date.parse(time);
  const times = wind.times.map((x) => Date.parse(x));
  if (!times.length || Number.isNaN(t)) return null;
  const last = times.length - 1;
  if (t <= times[0]) return { u: wind.u[0], v: wind.v[0] };
  if (t >= times[last]) return { u: wind.u[last], v: wind.v[last] };
  const k = times.findIndex((x) => x > t) - 1;
  const w = (t - times[k]) / (times[k + 1] - times[k]);
  const mix = (a: (number | null)[], b: (number | null)[]) =>
    a.map((x, i) => {
      const y = b[i];
      return x === null || y === null ? null : x + (y - x) * w;
    });
  return { u: mix(wind.u[k], wind.u[k + 1]), v: mix(wind.v[k], wind.v[k + 1]) };
}

/** Bilinear wind (m/s east, north) at a point; null outside the grid or next to a missing value.
 * Written without temporary arrays: it runs for every particle on every frame. */
export function sample(grid: WindGrid, field: Field, lon: number, lat: number): [number, number] | null {
  const x = (lon - grid.lon0) / grid.dlon;
  const y = (lat - grid.lat0) / grid.dlat;
  if (!(x >= 0 && y >= 0 && x <= grid.nx - 1 && y <= grid.ny - 1)) return null;
  const i = Math.min(Math.floor(x), grid.nx - 2);
  const j = Math.min(Math.floor(y), grid.ny - 2);
  const fx = x - i;
  const fy = y - j;
  const a = j * grid.nx + i;
  const b = a + grid.nx;
  const u00 = field.u[a], u10 = field.u[a + 1], u01 = field.u[b], u11 = field.u[b + 1];
  const v00 = field.v[a], v10 = field.v[a + 1], v01 = field.v[b], v11 = field.v[b + 1];
  if (u00 == null || u10 == null || u01 == null || u11 == null || v00 == null || v10 == null || v01 == null || v11 == null) {
    return null;
  }
  return [
    (u00 * (1 - fx) + u10 * fx) * (1 - fy) + (u01 * (1 - fx) + u11 * fx) * fy,
    (v00 * (1 - fx) + v10 * fx) * (1 - fy) + (v01 * (1 - fx) + v11 * fx) * fy,
  ];
}

/** The part of the view [west, south, east, north] the wind grid covers; null when they do not meet. */
export function spawnBox(grid: WindGrid, view: [number, number, number, number]): [number, number, number, number] | null {
  const west = Math.max(view[0], grid.lon0);
  const south = Math.max(view[1], grid.lat0);
  const east = Math.min(view[2], grid.lon0 + (grid.nx - 1) * grid.dlon);
  const north = Math.min(view[3], grid.lat0 + (grid.ny - 1) * grid.dlat);
  return west < east && south < north ? [west, south, east, north] : null;
}

/** Where air at (lon, lat) is after `seconds` in a wind of (u, v) m/s. */
export function advect(lon: number, lat: number, [u, v]: [number, number], seconds: number): [number, number] {
  return [lon + (u * seconds) / (METRES_PER_DEGREE * Math.cos((lat * Math.PI) / 180)), lat + (v * seconds) / METRES_PER_DEGREE];
}

/** Seconds of wind per animation frame so a 1 m/s wind moves a quarter of a pixel, at any zoom. */
export function secondsPerFrame(zoom: number): number {
  return (0.25 * EARTH_CIRCUMFERENCE_M) / (TILE * 2 ** zoom);
}

const mercX = (lon: number) => (lon + 180) / 360;
const mercY = (lat: number) => 0.5 - Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)) / (2 * Math.PI);

/** Web-mercator screen projection for an unrotated, flat map (cheap enough for thousands of particles a frame). */
export function projector(center: { lon: number; lat: number }, zoom: number, width: number, height: number) {
  const world = TILE * 2 ** zoom;
  const cx = mercX(center.lon) * world;
  const cy = mercY(center.lat) * world;
  return {
    toScreen(lon: number, lat: number): [number, number] {
      return [width / 2 + mercX(lon) * world - cx, height / 2 + mercY(lat) * world - cy];
    },
    toLngLat(x: number, y: number): [number, number] {
      const mx = (x - width / 2 + cx) / world;
      const my = (y - height / 2 + cy) / world;
      return [mx * 360 - 180, (360 / Math.PI) * Math.atan(Math.exp((0.5 - my) * 2 * Math.PI)) - 90];
    },
  };
}
