import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "vitest";

import { BANDS } from "./bands";

// The band word on its pill is how colour-blind parents read the band, so it must pass WCAG AA (4.5:1).
// Tests run from web/ (npm --prefix web test).
const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf8");

function token(name: string): string {
  const match = css.match(new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})`));
  if (!match) throw new Error(`missing --${name}`);
  return match[1];
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

test("every band word is readable on its colour (WCAG AA)", () => {
  for (const band of BANDS) {
    const [a, b] = [luminance(token(`band-${band}`)), luminance(token(`on-${band}`))];
    const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    expect(ratio, band).toBeGreaterThanOrEqual(4.5);
  }
});
