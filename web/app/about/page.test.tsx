import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { CLOSURE_CAPTION } from "@/components/ClosureNote";

import AboutPage from "./page";

test("explains both numbers and carries every credit and disclaimer", () => {
  render(<AboutPage />);
  expect(screen.getByText(CLOSURE_CAPTION)).toBeInTheDocument();
  const text = document.body.textContent ?? "";
  for (const phrase of ["24-hour average", "this hour's air", "not medical advice", "never asks for your location",
    "aqicn.org", "NASA FIRMS", "Open-Meteo", "Copernicus", "OpenStreetMap", "AGPL-3.0"]) {
    expect(text).toContain(phrase);
  }
});
