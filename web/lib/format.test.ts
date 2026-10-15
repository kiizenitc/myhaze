import { expect, test } from "vitest";

import { dateMYT, hourLabel, hourOfIso, hourStart, isStale, percent, timeMYT, weekdayDate } from "./format";

test("times show in Malaysia time whatever the device time zone", () => {
  // The test script runs with TZ=America/New_York.
  expect(timeMYT("2026-10-15T01:00:00Z")).toBe("9:00am");
  expect(timeMYT("2026-10-15T04:30:00Z")).toBe("12:30pm");
  expect(timeMYT("2026-10-15T16:05:00Z")).toBe("12:05am");
  expect(hourOfIso("2026-10-15T08:00:00Z")).toBe("4pm");
});

test("block hours and dates read naturally", () => {
  expect(["06:00", "12:00", "18:00", "00:00", "08:00"].map(hourLabel)).toEqual(["6am", "12pm", "6pm", "12am", "8am"]);
  expect(weekdayDate("2026-10-16")).toBe("Fri 16 Oct");
});

test("staleness and helpers", () => {
  const now = Date.parse("2026-10-15T05:00:00Z");
  expect(isStale("2026-10-15T04:00:00Z", now)).toBe(false);
  expect(isStale("2026-10-15T02:30:00Z", now)).toBe(true);
  expect(isStale("not a date", now)).toBe(true);
  expect(hourStart("2026-10-15T02:10:00Z")).toBe("2026-10-15T02:00:00.000Z");
  expect(percent(0.712)).toBe("71%");
  expect(percent(null)).toBe("–");
});


test("the Malaysia date of an instant", () => {
  expect(dateMYT("2026-10-15T15:59:00Z")).toBe("2026-10-15");
  expect(dateMYT("2026-10-15T16:00:00Z")).toBe("2026-10-16"); // midnight in Malaysia
});
