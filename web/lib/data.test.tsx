import { render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { useData } from "./data";

function Probe({ path }: { path: string | null }) {
  const { data, error } = useData<{ value: number }>(path);
  return <p>{error ? `error: ${error}` : data ? `value: ${data.value}` : "loading"}</p>;
}

test("loads JSON", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ value: 7 }), { status: 200 })));
  render(<Probe path="/data/x.json" />);
  await waitFor(() => expect(screen.getByText("value: 7")).toBeInTheDocument());
});

test("reports HTTP errors and skips a null path", async () => {
  const fetchMock = vi.fn(async () => new Response("nope", { status: 404 }));
  vi.stubGlobal("fetch", fetchMock);
  render(<Probe path="/data/missing.json" />);
  await waitFor(() => expect(screen.getByText("error: HTTP 404")).toBeInTheDocument());
  render(<Probe path={null} />);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});
