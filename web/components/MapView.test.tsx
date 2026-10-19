import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { GENERATED, makeMap, makeWind } from "@/test/fixtures";

import { MapView } from "./MapView";

const router = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
beforeEach(() => router.push.mockClear());

// MapLibre needs WebGL, which jsdom lacks; the map itself is checked in the browser (Task 8).
vi.mock("next/dynamic", () => ({
  default: () => function MapStub({ hour, animate, onPick }: { hour: number; animate: boolean; onPick: (id: string) => void }) {
    return <div data-testid="map">{`hour ${hour} animate ${animate}`}<button onClick={() => onPick("ZZ01A")}>tap station</button></div>;
  },
}));

test("the time slider steps through the 48 hours in Malaysia time, with a band legend", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => String(url).includes("wind.json")
    ? new Response("missing", { status: 404 }) // no wind file yet: the map still works without the flowing wind
    : new Response(JSON.stringify(String(url).includes("map.json") ? makeMap() : { generated_at: GENERATED, cells: [] }),
                   { status: 200 })));
  render(<MapView />);
  const slider = await screen.findByRole("slider", { name: "Time" });
  expect(screen.getByText("Now · Thu 15 Oct 10am")).toBeInTheDocument();
  expect(screen.getByText("Latest readings: 10am (updated 10:10am)")).toBeInTheDocument();
  fireEvent.change(slider, { target: { value: "14" } });
  expect(screen.getByTestId("map")).toHaveTextContent("hour 14");
  expect(screen.getByText("Forecast · Fri 16 Oct 12am")).toBeInTheDocument();
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
  render(<MapView />);
  expect(await screen.findByText("Lines show the wind that carries the smoke (about 120 m up) at Thu 15 Oct 10am."))
    .toBeInTheDocument();
  expect(screen.getByTestId("map")).toHaveTextContent("animate true");
  await userEvent.click(screen.getByRole("button", { name: "Pause wind" }));
  expect(screen.getByTestId("map")).toHaveTextContent("animate false");
  expect(screen.getByRole("button", { name: "Play wind" })).toBeInTheDocument();
});

test("tapping a station's dot opens that station's page", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(
    String(url).includes("map.json") ? makeMap() : { generated_at: GENERATED, cells: [] }),
    { status: String(url).includes("wind.json") ? 404 : 200 })));
  render(<MapView />);
  await userEvent.click(await screen.findByRole("button", { name: "tap station" }));
  expect(router.push).toHaveBeenCalledWith("/station/?id=ZZ01A");
});

test("Play runs the 48 hours as a time-lapse and stops at the end; Stop or the slider halts it", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(
    String(url).includes("map.json") ? makeMap() : { generated_at: GENERATED, cells: [] }),
    { status: String(url).includes("wind.json") ? 404 : 200 })));
  render(<MapView />);
  const slider = await screen.findByRole("slider", { name: "Time" });
  vi.useFakeTimers();
  try {
    fireEvent.click(screen.getByRole("button", { name: "Play the 48-hour forecast" }));
    act(() => vi.advanceTimersByTime(1500)); // three steps of half a second
    expect(screen.getByTestId("map")).toHaveTextContent("hour 3");
    expect(screen.getByText("Forecast · Thu 15 Oct 1pm")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Stop the time-lapse" }));
    act(() => vi.advanceTimersByTime(2000));
    expect(screen.getByTestId("map")).toHaveTextContent("hour 3");

    fireEvent.click(screen.getByRole("button", { name: "Play the 48-hour forecast" }));
    act(() => vi.advanceTimersByTime(60_000)); // runs to the last hour and stops there
    expect(screen.getByTestId("map")).toHaveTextContent("hour 47");
    expect(screen.getByRole("button", { name: "Play the 48-hour forecast" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Play the 48-hour forecast" })); // at the end: starts again
    act(() => vi.advanceTimersByTime(500));
    expect(screen.getByTestId("map")).toHaveTextContent("hour 1");
    fireEvent.change(slider, { target: { value: "10" } }); // dragging the slider takes over
    act(() => vi.advanceTimersByTime(2000));
    expect(screen.getByTestId("map")).toHaveTextContent("hour 10");
  } finally {
    vi.useRealTimers();
  }
});

test("the map says plainly that later hours are a forecast, with links to how it works and how accurate it is", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(
    String(url).includes("map.json") ? makeMap() : { generated_at: GENERATED, cells: [] }),
    { status: String(url).includes("wind.json") ? 404 : 200 })));
  render(<MapView />);
  const note = await screen.findByRole("note");
  expect(note).toHaveTextContent("Forecast, not a measurement");
  expect(within(note).getByRole("link", { name: "How the forecast works" })).toHaveAttribute("href", "/about/#how");
  expect(within(note).getByRole("link", { name: "How accurate it is" })).toHaveAttribute("href", "/accuracy/");
});
