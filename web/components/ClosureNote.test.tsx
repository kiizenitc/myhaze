import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { CLOSURE_CAPTION, ClosureNote } from "./ClosureNote";

test("shows the chance, the rule and the fixed MOE caption", () => {
  render(<ClosureNote closure={{ school_day: "2026-10-16", probability: 0.62, rule: "three_days_above_150" }} />);
  const note = screen.getByRole("region", { name: "School closure indicator" });
  expect(note).toHaveTextContent("School closure rule for Fri 16 Oct: Possible (62%)");
  expect(note).toHaveTextContent("mainly through the official API staying above 150 for three days running.");
  expect(screen.getByText(CLOSURE_CAPTION)).toBeInTheDocument();
});

test("a missing probability reads as a sentence and keeps the caption", () => {
  const { container } = render(<ClosureNote closure={{ school_day: "2026-10-18", probability: null, rule: null }} />);
  expect(screen.getByText(/not enough forecast yet/)).toBeInTheDocument();
  expect(container.textContent).not.toMatch(/null|NaN/);
  expect(screen.getByText(CLOSURE_CAPTION)).toBeInTheDocument();
});
