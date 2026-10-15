import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { Footer } from "./Footer";

test("footer credits every data source and carries the MOE and medical disclaimers", () => {
  render(<Footer />);
  expect(screen.getByText(/follow official MOE announcements/i)).toBeInTheDocument();
  expect(screen.getByText(/not medical advice/i)).toBeInTheDocument();
  const credits = screen.getByText(/Department of Environment Malaysia \(DOE\)/);
  for (const source of ["aqicn.org", "NASA FIRMS", "Open-Meteo", "CAMS"]) {
    expect(credits.textContent).toContain(source);
  }
});
