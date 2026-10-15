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
    load();
    const timer = setInterval(load, refreshMs);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [path, refreshMs]);
  return state;
}
