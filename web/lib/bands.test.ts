import { expect, test } from "vitest";

import { ADVICE, BAND_LABEL, BANDS, adviceFor } from "./bands";

test("every band has a label and advice", () => {
  for (const band of BANDS) {
    expect(BAND_LABEL[band]).toBeTruthy();
    expect(ADVICE[band]).toBeTruthy();
  }
  expect(BAND_LABEL.very_unhealthy).toBe("Very unhealthy");
});

test("the sensitive switch uses the next stricter band's advice", () => {
  expect(adviceFor("moderate", false)).toBe(ADVICE.moderate);
  expect(adviceFor("moderate", true)).toBe(ADVICE.unhealthy);
  expect(adviceFor("hazardous", true)).toBe(ADVICE.hazardous);
});

test("advice never tells parents to keep children home", () => {
  for (const band of BANDS) expect(ADVICE[band].toLowerCase()).not.toContain("keep your child home");
});
