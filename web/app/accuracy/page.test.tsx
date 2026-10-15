import { render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { makeAccuracy } from "@/test/fixtures";

import AccuracyPage from "./page";

function serve(body: unknown) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
}

test("backtest tables compare every method, mark the one in use and say plainly that the target is not met", async () => {
  serve(makeAccuracy());
  render(<AccuracyPage />);
  expect(await screen.findByRole("heading", { name: "Tomorrow" })).toBeInTheDocument();
  const tomorrow = screen.getAllByRole("table")[0];
  expect(within(tomorrow).getByText("71%")).toBeInTheDocument();
  expect(within(tomorrow).getByText("58%")).toBeInTheDocument();
  expect(within(tomorrow).getByText(/used on this site/).closest("tr")).toHaveTextContent("MYHaze model");
  expect(screen.getByText(/Target not met yet/)).toBeInTheDocument();
  expect(screen.getByText(/live track record starts/)).toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(/NaN|null|undefined/);
});

test("the live track record shows the checked hours", async () => {
  serve({ ...makeAccuracy(), track_record: {
    "1-24h": { days: 3, hours: 4800, band_accuracy: 0.74, unhealthy_hours: 900, pod_unhealthy: 0.8 } } });
  render(<AccuracyPage />);
  const row = (await screen.findByText("Next 24 hours")).closest("tr")!;
  expect(row).toHaveTextContent("74%");
  expect(row).toHaveTextContent("4800 hours");
});

test("the honest limits are stated", async () => {
  serve(makeAccuracy());
  render(<AccuracyPage />);
  expect(await screen.findByText(/a few points higher or lower/)).toBeInTheDocument();
  expect(screen.getByText(/only the live track record/)).toBeInTheDocument();
});
