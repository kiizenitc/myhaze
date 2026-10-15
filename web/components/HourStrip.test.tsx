import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import type { Band } from "@/lib/bands";

import { HourStrip } from "./HourStrip";

test("every hour is coloured and named, with a legend of the bands present", () => {
  const bands: Band[] = ["moderate", ...Array<Band>(23).fill("unhealthy")];
  render(<HourStrip bands={bands} start="2026-10-15T02:00:00Z" />);
  expect(screen.getAllByRole("img")).toHaveLength(24);
  expect(screen.getByRole("img", { name: "10am: Moderate" })).toBeInTheDocument();
  expect(screen.getByText("Unhealthy")).toBeInTheDocument();
  expect(screen.queryByText("Hazardous")).toBeNull();
});
