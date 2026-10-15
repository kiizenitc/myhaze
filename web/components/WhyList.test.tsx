import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { WhyList } from "./WhyList";

test("lists the reasons", () => {
  render(<WhyList why={["Fires upwind are adding smoke.", "Rain on the way should help clear the air."]} estimated={false} />);
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
});

test("no reasons, and an estimated station, read as sentences", () => {
  render(<WhyList why={[]} estimated />);
  expect(screen.getByText(/No single strong reason/)).toBeInTheDocument();
  expect(screen.getByText(/no hourly feed right now/)).toBeInTheDocument();
});
