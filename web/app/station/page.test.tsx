import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { CLOSURE_CAPTION } from "@/components/ClosureNote";
import { ADVICE } from "@/lib/bands";
import { loadSaved, loadSensitive } from "@/lib/saved";
import { makeStation } from "@/test/fixtures";

import { StationView } from "./StationView";

const search = vi.hoisted(() => ({ value: "id=ZZ01A" }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(search.value) }));

beforeEach(() => {
  search.value = "id=ZZ01A";
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(makeStation("ZZ01A")), { status: 200 })));
});

test("shows now, the plan for tomorrow, the reasons, the official outlook and the closure note", async () => {
  render(<StationView />);
  expect(await screen.findByRole("heading", { level: 1, name: "Testville" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { selected: true })).toHaveTextContent("Fri 16 Oct");
  expect(screen.getByText("Fires upwind, mainly in Sumatra, are adding smoke.")).toBeInTheDocument();
  expect(screen.getByText(/Highest 24-hour average/)).toHaveTextContent("about 160 around Thu 15 Oct 10am (likely 150–175)");
  expect(screen.getByText(CLOSURE_CAPTION)).toBeInTheDocument();
});

test("the sensitive switch makes the advice one band stricter and is remembered", async () => {
  render(<StationView />);
  expect(await screen.findByText(ADVICE.very_unhealthy)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("switch"));
  expect(screen.getByText(ADVICE.hazardous)).toBeInTheDocument();
  expect(loadSensitive()).toBe(true);
});

test("the hour-by-hour forecast opens from the plan", async () => {
  render(<StationView />);
  await userEvent.click(await screen.findByRole("button", { name: "See hour-by-hour forecast" }));
  expect(screen.getByRole("img", { name: /Hour-by-hour forecast chart/ })).toBeInTheDocument();
});

test("saving the station remembers it", async () => {
  render(<StationView />);
  await userEvent.click(await screen.findByRole("button", { name: /Save Testville/ }));
  expect(loadSaved()).toEqual(["ZZ01A"]);
  expect(screen.getByRole("button", { name: /Saved Testville/ })).toHaveAttribute("aria-pressed", "true");
});

test.each(["", "../latest", "zz01a", "A".repeat(13), "ZZ01A/../x"])("an untrusted id %j is never fetched", (bad) => {
  search.value = `id=${encodeURIComponent(bad)}`;
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<StationView />);
  expect(screen.getByRole("heading", { name: "Station not found" })).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("an unknown station reads as not found", async () => {
  search.value = "id=ZZ99Z";
  vi.stubGlobal("fetch", vi.fn(async () => new Response("missing", { status: 404 })));
  render(<StationView />);
  expect(await screen.findByRole("heading", { name: "Station not found" })).toBeInTheDocument();
});
