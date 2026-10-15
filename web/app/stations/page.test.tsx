import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { loadSaved } from "@/lib/saved";
import { makeLatest } from "@/test/fixtures";

import StationsPage from "./page";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(makeLatest()), { status: 200 })));
});

test("lists every station by state and narrows the list as you type", async () => {
  render(<StationsPage />);
  expect(await screen.findAllByRole("heading", { level: 2 })).toHaveLength(2);
  await userEvent.type(screen.getByRole("searchbox"), "sample");
  expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual(["Johor"]);
  await userEvent.clear(screen.getByRole("searchbox"));
  await userEvent.type(screen.getByRole("searchbox"), "nowhere");
  expect(screen.getByText(/No station matches/)).toBeInTheDocument();
});

test("saving from the list remembers the station", async () => {
  render(<StationsPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Save Testville/ }));
  expect(loadSaved()).toEqual(["ZZ01A"]);
});
