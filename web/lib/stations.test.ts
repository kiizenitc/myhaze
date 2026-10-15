import { expect, test } from "vitest";

import { makeLatest } from "@/test/fixtures";

import { filterStations, groupByState } from "./stations";

test("search matches name, state or id, ignoring case and word order", () => {
  const all = makeLatest().stations;
  expect(filterStations(all, "selangor").map((s) => s.id)).toEqual(["ZZ01A", "ZZ03C"]);
  expect(filterStations(all, "contoh KAMPUNG").map((s) => s.id)).toEqual(["ZZ03C"]);
  expect(filterStations(all, "zz02b").map((s) => s.id)).toEqual(["ZZ02B"]);
  expect(filterStations(all, "   ")).toHaveLength(3);
});

test("stations are grouped by state, both in alphabetical order", () => {
  expect(groupByState(makeLatest().stations).map(([state, list]) => [state, list.map((s) => s.name)])).toEqual([
    ["Johor", ["Sampleton"]],
    ["Selangor", ["Kampung Contoh", "Testville"]],
  ]);
});
