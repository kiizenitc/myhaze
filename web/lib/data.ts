"use client";

import { useEffect, useState } from "react";

export function useData<T>(path: string | null, refreshMs = 600_000): { data?: T; error?: string } {
  const [state, setState] = useState<{ data?: T; error?: string }>({});
  useEffect(() => {
    if (!path) return;
    let alive = true;
    const load = () =>
      fetch(path, { cache: "no-store" })
        .then((response) => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response.json() as Promise<T>;
        })
        .then(
          (data) => alive && setState({ data }),
          (error: unknown) =>
            alive && setState((previous) => ({ data: previous.data, error: error instanceof Error ? error.message : String(error) })),
        );
    // Phones freeze background timers: refresh as soon as the page is seen again or the network returns.
    const onVisible = () => {
      if (document.visibilityState !== "hidden") load();
    };
    load();
    const timer = setInterval(load, refreshMs);
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("pageshow", load);
    window.addEventListener("online", load);
    return () => {
      alive = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("pageshow", load);
      window.removeEventListener("online", load);
    };
  }, [path, refreshMs]);
  return state;
}
