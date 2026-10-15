import { expect, test, vi } from "vitest";

import { loadSaved, loadSensitive, saveSaved, saveSensitive, toggleSaved } from "./saved";

test("saved stations round-trip, de-duplicated and in order", () => {
  saveSaved(["CA21B", "CA01R", "CA21B"]);
  expect(loadSaved()).toEqual(["CA21B", "CA01R"]);
  expect(toggleSaved("CA01R")).toEqual(["CA21B"]);
  expect(toggleSaved("CA44Q")).toEqual(["CA21B", "CA44Q"]);
});

test("corrupted or blocked storage fails quietly", () => {
  localStorage.setItem("myhaze.saved.v1", "{not json");
  expect(loadSaved()).toEqual([]);
  localStorage.setItem("myhaze.saved.v1", JSON.stringify([1, "CA21B", null]));
  expect(loadSaved()).toEqual(["CA21B"]);
  const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  expect(loadSaved()).toEqual([]);
  expect(loadSensitive()).toBe(false);
  spy.mockRestore();
  const setSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("full"); });
  expect(() => saveSaved(["CA21B"])).not.toThrow();
  expect(() => saveSensitive(true)).not.toThrow();
  setSpy.mockRestore();
});

test("sensitive switch round-trips", () => {
  expect(loadSensitive()).toBe(false);
  saveSensitive(true);
  expect(loadSensitive()).toBe(true);
});
