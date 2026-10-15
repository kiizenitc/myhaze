import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { GENERATED, makeMap } from "@/test/fixtures";

import MapPage from "./page";

// MapLibre needs WebGL, which jsdom lacks; the map itself is checked in the browser (Task 8).
vi.mock("next/dynamic", () => ({
  default: () => function MapStub({ hour }: { hour: number }) {
    return <div data-testid="map">{`hour ${hour}`}</div>;
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
  expect(screen.getByText(/Moving lines show the wind/)).toBeInTheDocument();
  expect(screen.getByText(/Data delayed/)).toBeInTheDocument(); // the fixture is hours old (the slider output is a status too)
  for (const word of ["Good", "Moderate", "Unhealthy", "Very unhealthy", "Hazardous"]) {
    expect(screen.getByText(word)).toBeInTheDocument();
  }
});
