import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { saveSaved } from "@/lib/saved";
import { makeLatest } from "@/test/fixtures";

import Home from "./page";

function serve(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
}

test("with nothing saved, the home page invites choosing stations", async () => {
  serve(makeLatest());
  render(<Home />);
  expect(await screen.findByRole("link", { name: "Choose your stations" })).toHaveAttribute("href", "/stations/");
});

test("saved stations show as cards, in the order they were saved", async () => {
  saveSaved(["ZZ03C", "ZZ01A"]);
  serve(makeLatest());
  render(<Home />);
  const names = await screen.findAllByRole("heading", { level: 2 });
  expect(names.map((h) => h.textContent)).toEqual(["Kampung Contoh", "Testville"]);
  expect(screen.getAllByText(/Updated 10:10am/)).toHaveLength(2);
});

test("a failed load shows a friendly message, not a blank page", async () => {
  saveSaved(["ZZ01A"]);
  vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
  render(<Home />);
  expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't load the latest readings");
});
