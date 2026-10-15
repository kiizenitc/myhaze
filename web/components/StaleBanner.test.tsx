import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { StaleBanner } from "./StaleBanner";

test("appears only when the data is over two hours old", () => {
  const now = Date.parse("2026-10-15T05:00:00Z");
  const { rerender } = render(<StaleBanner generatedAt="2026-10-15T04:10:00Z" now={now} />);
  expect(screen.queryByRole("status")).toBeNull();
  rerender(<StaleBanner generatedAt="2026-10-15T02:10:00Z" now={now} />);
  expect(screen.getByRole("status")).toHaveTextContent("Data delayed. Last updated Thu 15 Oct at 10:10am.");
});
