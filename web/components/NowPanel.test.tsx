import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { ADVICE } from "@/lib/bands";
import { makeStation } from "@/test/fixtures";

import { NowPanel } from "./NowPanel";

test("Real Feel is this hour's air and the official API is a 24-hour average", () => {
  render(<NowPanel now={makeStation().now} sensitive={false} />);
  expect(screen.getByText(/this hour's air/)).toBeInTheDocument();
  expect(screen.getByText(/24-hour average/)).toBeInTheDocument();
  expect(screen.getByText("214")).toBeInTheDocument();
  expect(screen.getByText("Very unhealthy")).toBeInTheDocument();
  expect(screen.getByText(ADVICE.very_unhealthy)).toBeInTheDocument();
  expect(screen.getByText("PM2.5 92.1 µg/m³ at 10:00am")).toBeInTheDocument();
  expect(screen.getByText("DOE's figure for 10:00am")).toBeInTheDocument();
});

test("an estimated station explains the missing reading and never prints null", () => {
  const { container } = render(<NowPanel now={makeStation("ZZ02B", { estimated: true }).now} sensitive />);
  expect(screen.getByText(/No hourly reading/)).toBeInTheDocument();
  expect(container.textContent).not.toMatch(/null|NaN|undefined/);
  // Advice falls back to the official band (unhealthy), one band stricter for a sensitive child.
  expect(screen.getByText(ADVICE.very_unhealthy)).toBeInTheDocument();
});

test("names the pollutant that sets Real Feel when it is not PM2.5", () => {
  const now = { ...makeStation().now, real_feel: 72, real_feel_band: "moderate" as const, main_pollutant: "o3" as const,
    pm25: 9.6 };
  render(<NowPanel now={now} sensitive={false} />);
  expect(screen.getByText("Ozone is highest this hour · PM2.5 9.6 µg/m³ at 10:00am")).toBeInTheDocument();
});
