import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { GENERATED, makeMap, makeWind } from "@/test/fixtures";

import MapPage from "./page";

// MapLibre needs WebGL, which jsdom lacks; the map itself is checked in the browser (Task 8).
vi.mock("next/dynamic", () => ({
  default: () => function MapStub({ hour, animate }: { hour: number; animate: boolean }) {
    return <div data-testid="map">{`hour ${hour} animate ${animate}`}</div>;
  },
}));

test("the time slider steps through the 48 hours in Malaysia time, with a band legend", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => String(url).includes("wind.json")
    ? new Response("missing", { status: 404 }) // no wind file yet: the map still works without the flowing wind
    : new Response(JSON.stringify(String(url).includes("map.json") ? makeMap() : { generated_at: GENERATED, cells: [] }),
                   { status: 200 })));
  render(<MapPage />);
  const slider = await screen.findByRole("slider", { name: "Time" });
  expect(screen.getByText("Thu 15 Oct 10am")).toBeInTheDocument();
  fireEvent.change(slider, { target: { value: "14" } });
  expect(screen.getByTestId("map")).toHaveTextContent("hour 14");
  expect(screen.getByText("Fri 16 Oct 12am")).toBeInTheDocument();
  expect(await screen.findByText("Wind lines are not available right now.")).toBeInTheDocument();
  expect(screen.getByText(/Data delayed/)).toBeInTheDocument(); // the fixture is hours old (the slider output is a status too)
  for (const word of ["Good", "Moderate", "Unhealthy", "Very unhealthy", "Hazardous"]) {
    expect(screen.getByText(word)).toBeInTheDocument();
  }
});

test("the wind can be paused, and the caption says what the lines are", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(
    String(url).includes("wind.json") ? makeWind() : String(url).includes("map.json") ? makeMap()
      : { generated_at: GENERATED, cells: [] }), { status: 200 })));
  render(<MapPage />);
  expect(await screen.findByText(/Lines show the wind that carries the smoke/)).toBeInTheDocument();
  expect(screen.getByTestId("map")).toHaveTextContent("animate true");
  await userEvent.click(screen.getByRole("button", { name: "Pause wind" }));
  expect(screen.getByTestId("map")).toHaveTextContent("animate false");
  expect(screen.getByRole("button", { name: "Play wind" })).toBeInTheDocument();
});
