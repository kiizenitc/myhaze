import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";

import { makeHours } from "@/test/fixtures";

import { HourlyChart, compass } from "./HourlyChart";

test("draws the Real Feel range, the Real Feel line and the official API line, with a legend", () => {
  render(<HourlyChart hours={makeHours()} />);
  const chart = screen.getByRole("img", { name: /Hour-by-hour forecast chart/ });
  expect(chart.querySelectorAll("path[data-series]")).toHaveLength(3);
  expect(screen.getByText("Real Feel (likely)")).toBeInTheDocument();
  expect(screen.getByText("Official API (24-hour average)")).toBeInTheDocument();
});

test("hovering shows that hour's numbers in Malaysia time", () => {
  render(<HourlyChart hours={makeHours()} />);
  const chart = screen.getByRole("img", { name: /Hour-by-hour forecast chart/ });
  chart.getBoundingClientRect = () => ({ left: 0, top: 0, width: 720, height: 290, right: 720, bottom: 290, x: 0, y: 0, toJSON: () => ({}) });
  fireEvent.mouseMove(chart, { clientX: 50, clientY: 100 }); // the first hour
  const tip = screen.getByRole("tooltip");
  expect(tip).toHaveTextContent("Thu 15 Oct 10am");
  expect(tip).toHaveTextContent("Real Feel 150 Unhealthy");
  expect(tip).toHaveTextContent("Official API 160");
});

test("the table view lists all 48 hours", async () => {
  render(<HourlyChart hours={makeHours()} />);
  await userEvent.click(screen.getByRole("button", { name: "Show as table" }));
  expect(screen.getAllByRole("row")).toHaveLength(49);
  expect(screen.getAllByText("8 km/h from the south-west").length).toBeGreaterThan(0);
});

test("compass", () => {
  expect([0, 44, 90, 225, 350, -45].map(compass)).toEqual(["north", "north-east", "east", "south-west", "north", "north-west"]);
});

test("tapping a point shows that hour's numbers (phones send taps, not hovers)", () => {
  render(<HourlyChart hours={makeHours()} />);
  const chart = screen.getByRole("img", { name: /Hour-by-hour forecast chart/ });
  chart.getBoundingClientRect = () => ({ left: 0, top: 0, width: 720, height: 290, right: 720, bottom: 290, x: 0, y: 0, toJSON: () => ({}) });
  fireEvent.click(chart, { clientX: 712, clientY: 100 }); // the last hour
  expect(screen.getByRole("tooltip")).toHaveTextContent("Sat 17 Oct 9am");
});
