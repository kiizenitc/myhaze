"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { StaleBanner } from "@/components/StaleBanner";
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

  if (saved === null) return <p>Loading…</p>;
  if (saved.length === 0) {
    return (
      <section className="py-10 text-center">
        <h1 className="text-2xl font-semibold">Haze Real Feel for your child&apos;s day</h1>
        <p className="mt-2 text-[var(--ink-2)]">
          Pick the stations near home, school, tuition or sports to see this hour&apos;s air and the next 48 hours.
        </p>
        <Link href="/stations/" className="mt-6 inline-block rounded-full bg-[var(--accent)] px-5 py-2.5 font-semibold text-[var(--page)]">
          Choose your stations
        </Link>
      </section>
    );
  }
  if (!data) {
    return error ? (
      <p role="alert" className="py-6">
        We couldn&apos;t load the latest readings. Check your connection; the page tries again every few minutes.
      </p>
    ) : (
      <p>Loading…</p>
    );
  }
  const byId = new Map(data.stations.map((s) => [s.id, s]));
  const cards = saved.map((id) => byId.get(id)).filter((s): s is StationSummary => s !== undefined);
  return (
    <>
      <StaleBanner generatedAt={data.generated_at} />
      <div className="grid gap-4">
        {cards.map((s) => <StationCard key={s.id} station={s} generatedAt={data.generated_at} sensitive={sensitive} />)}
      </div>
      <p className="mt-6 text-center">
        <Link href="/stations/" className="text-[var(--accent)] underline">Add or remove stations</Link>
      </p>
    </>
  );
}
