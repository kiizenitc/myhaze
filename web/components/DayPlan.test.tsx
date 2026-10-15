import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { makeDays } from "@/test/fixtures";

import { DayPlan } from "./DayPlan";

test("opens on tomorrow, with tabs labelled by date and each block's worst hour", () => {
  render(<DayPlan days={makeDays()} />);
  expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Thu 15 Oct", "Fri 16 Oct", "Sat 17 Oct"]);
  expect(screen.getByRole("tab", { selected: true })).toHaveTextContent("Fri 16 Oct");
  expect(screen.getByText("worst ~8am")).toBeInTheDocument();
  expect(screen.getByText("Very unhealthy")).toBeInTheDocument();
  expect(screen.getByText(/Best window outdoors/)).toHaveTextContent("Best window outdoors: 1pm–5pm (Moderate)");
});

test("past and unavailable blocks, and a day without a window, read as sentences", async () => {
  render(<DayPlan days={makeDays()} />);
  await userEvent.click(screen.getByRole("tab", { name: "Thu 15 Oct" }));
  expect(screen.getByText("Already passed")).toBeInTheDocument();
  expect(screen.getByText(/No clear stretch of good or moderate air/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: "Sat 17 Oct" }));
  expect(screen.getAllByText("Beyond the 48-hour forecast")).toHaveLength(2);
});

test("the hour-by-hour link asks for the hourly forecast", async () => {
  const onShowHours = vi.fn();
  render(<DayPlan days={makeDays()} onShowHours={onShowHours} />);
  await userEvent.click(screen.getByRole("button", { name: "See hour-by-hour forecast" }));
  expect(onShowHours).toHaveBeenCalledTimes(1);
});
