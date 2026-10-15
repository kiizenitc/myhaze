"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { MapView } from "@/components/MapView";
import { StationCard } from "@/components/StationCard";
import { useData } from "@/lib/data";
import { loadSaved, loadSensitive } from "@/lib/saved";
import type { Latest, StationSummary } from "@/lib/types";

export default function Home() {
  const { data, error } = useData<Latest>("/data/latest.json");
  const [saved, setSaved] = useState<string[] | null>(null);
  const [sensitive, setSensitive] = useState(false);
  useEffect(() => {
    // localStorage exists only in the browser, so it is read after the first render.
    setSaved(loadSaved());
    setSensitive(loadSensitive());
  }, []);

  const byId = new Map((data?.stations ?? []).map((s) => [s.id, s]));
  const cards = (saved ?? []).map((id) => byId.get(id)).filter((s): s is StationSummary => s !== undefined);
  return (
    <>
      <MapView />
      <section aria-labelledby="mine" className="mt-10">
        <h2 id="mine" className="text-xl font-semibold">Your stations</h2>
        {saved === null ? (
          <p className="mt-2">Loading…</p>
        ) : saved.length === 0 ? (
          <div className="mt-2">
            <p className="text-[var(--ink-2)]">
              Save the stations near home, school, tuition or sports to see this hour&apos;s air and the next 48 hours here.
            </p>
            <Link href="/stations/" className="mt-4 inline-block rounded-full bg-[var(--accent)] px-5 py-2.5 font-semibold text-[var(--page)]">
              Choose your stations
            </Link>
          </div>
        ) : !data ? (
          error ? (
            <p role="alert" className="mt-2">
              We couldn&apos;t load the latest readings. Check your connection; the page tries again every few minutes.
            </p>
          ) : (
            <p className="mt-2">Loading…</p>
          )
        ) : (
          <>
            <div className="mt-3 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {cards.map((s) => <StationCard key={s.id} station={s} generatedAt={data.generated_at} sensitive={sensitive} />)}
            </div>
            <p className="mt-6">
              <Link href="/stations/" className="text-[var(--accent)] underline">Add or remove stations</Link>
            </p>
          </>
        )}
      </section>
    </>
  );
}
