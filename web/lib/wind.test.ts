import { expect, test } from "vitest";

import type { WindData } from "./types";
import { advect, fieldAt, projector, sample } from "./wind";

const WIND: WindData = {
  generated_at: "2026-10-15T02:10:00Z",
  grid: { lon0: 100, lat0: 0, dlon: 1, dlat: 1, nx: 2, ny: 2 },
  times: ["2026-10-15T02:00:00Z", "2026-10-15T05:00:00Z"],
  u: [[1, 3, 5, 7], [4, 6, 8, 10]],
  v: [[0, 0, 0, 0], [3, 3, 3, null]],
};
const round = (xs: (number | null)[]) => xs.map((x) => (x === null ? null : Math.round(x * 1000) / 1000));

test("between two 3-hourly frames the field is interpolated; before and after it is held", () => {
  const at3 = fieldAt(WIND, "2026-10-15T03:00:00Z")!;
  expect(round(at3.u)).toEqual([2, 4, 6, 8]);
  expect(round(at3.v)).toEqual([1, 1, 1, null]); // a gap in either frame stays a gap
  expect(fieldAt(WIND, "2026-10-15T00:00:00Z")!.u).toEqual(WIND.u[0]);
  expect(fieldAt(WIND, "2026-10-16T00:00:00Z")!.u).toEqual(WIND.u[1]);
});

test("the wind between grid points is bilinear; outside the grid or next to a gap there is none", () => {
  const first = { u: WIND.u[0], v: WIND.v[0] };
  expect(sample(WIND.grid, first, 100.5, 0.5)).toEqual([4, 0]);
  expect(sample(WIND.grid, first, 100, 0)).toEqual([1, 0]);
  expect(sample(WIND.grid, first, 101, 1)).toEqual([7, 0]);
  expect(sample(WIND.grid, first, 99.9, 0.5)).toBeNull();
  expect(sample(WIND.grid, { u: WIND.u[1], v: WIND.v[1] }, 100.5, 0.5)).toBeNull();
});

test("air moves east and north at the wind's speed, further in longitude away from the equator", () => {
  const [lon, lat] = advect(110, 0, [10, 10], 1000);
  expect(lon - 110).toBeCloseTo(10_000 / 111_320, 6);
  expect(lat).toBeCloseTo(10_000 / 111_320, 6);
  expect(advect(110, 60, [10, 0], 1000)[0] - 110).toBeCloseTo(20_000 / 111_320, 6);
});

test("the screen projection matches web mercator and inverts", () => {
  const p = projector({ lon: 110, lat: 4 }, 4, 400, 300);
  expect(p.toScreen(110, 4)).toEqual([200, 150]);
  expect(p.toScreen(111, 4)[0]).toBeCloseTo(200 + (512 * 16) / 360, 6);
  expect(p.toScreen(110, 5)[1]).toBeLessThan(150); // north is up
  const [lon, lat] = p.toLngLat(...p.toScreen(105, -2));
  expect(lon).toBeCloseTo(105, 6);
  expect(lat).toBeCloseTo(-2, 6);
});
