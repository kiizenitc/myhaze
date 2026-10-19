import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { saveSaved } from "@/lib/saved";
import { makeLatest, makeMap } from "@/test/fixtures";

import Home from "./page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("next/dynamic", () => ({ default: () => function MapStub() { return <div data-testid="map" />; } }));

function serve(latest: unknown) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (String(url).includes("latest.json")) return new Response(JSON.stringify(latest), { status: 200 });
    if (String(url).includes("map.json")) return new Response(JSON.stringify(makeMap()), { status: 200 });
    return new Response("missing", { status: 404 });
  }));
}

test("the home page opens on the map, and with nothing saved invites choosing stations", async () => {
  serve(makeLatest());
  render(<Home />);
  expect(await screen.findByTestId("map")).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: "Choose your stations" })).toHaveAttribute("href", "/stations/");
});

test("saved stations show as cards, in the order they were saved", async () => {
  saveSaved(["ZZ03C", "ZZ01A"]);
  serve(makeLatest());
  render(<Home />);
  const names = await screen.findAllByRole("heading", { level: 3 });
  expect(names.map((h) => h.textContent)).toEqual(["Kampung Contoh", "Testville"]);
  expect(screen.getAllByText(/Updated (Thu 15 Oct, )?10:10am/)).toHaveLength(2); // the date shows once the fixture is not from today
});

test("a failed load shows a friendly message, not a blank page", async () => {
  saveSaved(["ZZ01A"]);
  vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
  render(<Home />);
  const alerts = await screen.findAllByRole("alert");
  expect(alerts.some((a) => a.textContent?.includes("We couldn't load the latest readings"))).toBe(true);
});
