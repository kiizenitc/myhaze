import { expect, test } from "vitest";

import { GENERATED, makeMap } from "@/test/fixtures";

import { firesCollection, stationsAt } from "./geojson";

test("station points carry the chosen hour's band and Real Feel number", () => {
  const first = stationsAt(makeMap(), 0).features[0];
  expect(first.geometry.coordinates).toEqual([101.5, 3.0]);
  expect(first.properties).toEqual({ id: "ZZ01A", name: "Testville", band: "unhealthy", rf: 150 });
  expect(stationsAt(makeMap(), 3).features[0].properties.rf).toBe(165);
});

test("fire cells become points at longitude, latitude", () => {
  expect(firesCollection({ generated_at: GENERATED, cells: [[-1.5, 110.25, 812.4]] }).features[0]).toEqual({
    type: "Feature", geometry: { type: "Point", coordinates: [110.25, -1.5] }, properties: { frp: 812.4 },
  });
  expect(firesCollection(undefined).features).toEqual([]);
});
