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

function Fast() {
  const { data, error } = useData<{ value: number }>("/data/x.json", 30);
  return <p>{error ? `error: ${error}` : data ? `value: ${data.value}` : "loading"}</p>;
}

test("a later successful refresh clears the error", async () => {
  let calls = 0;
  vi.stubGlobal("fetch", vi.fn(async () =>
    ++calls === 1 ? new Response("down", { status: 503 }) : new Response(JSON.stringify({ value: 9 }), { status: 200 })));
  render(<Fast />);
  await waitFor(() => expect(screen.getByText("error: HTTP 503")).toBeInTheDocument());
  await waitFor(() => expect(screen.getByText("value: 9")).toBeInTheDocument());
});

test("coming back to the page (phone unlocked, tab reopened, back online) refreshes at once", async () => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ value: 1 }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  render(<Probe path="/data/x.json" />);
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  document.dispatchEvent(new Event("visibilitychange"));
  window.dispatchEvent(new Event("online"));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
});
