"use client";

import Link from "next/link";
import { useState } from "react";

import { BandPill } from "@/components/BandPill";
import { SaveToggle } from "@/components/SaveToggle";
import { useData } from "@/lib/data";
import { filterStations, groupByState } from "@/lib/stations";
import type { Latest } from "@/lib/types";

export default function StationsPage() {
  const { data, error } = useData<Latest>("/data/latest.json");
  const [query, setQuery] = useState("");
  const groups = data ? groupByState(filterStations(data.stations, query)) : [];
  return (
    <section>
      <h1 className="text-2xl font-semibold">Choose your stations</h1>
      <p className="mt-1 text-[var(--ink-2)]">
        Save the stations closest to home, school, tuition or sports. Saved stations show on the home page, on this
        device only.
      </p>
      <p className="mt-1"><Link href="/map/" className="text-[var(--accent)] underline">Find stations on the map</Link></p>
      <label className="mt-4 block">
        <span className="text-sm font-medium">Search</span>
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Town, state or station id"
               className="mt-1 w-full rounded-lg border border-[var(--line)] bg-[var(--card)] px-3 py-2" />
      </label>
      {!data ? (
        error ? <p role="alert" className="mt-4">We couldn&apos;t load the station list. Check your connection; the page tries again every few minutes.</p>
          : <p className="mt-4">Loading…</p>
      ) : groups.length === 0 ? (
        <p className="mt-4">{`No station matches “${query.trim()}”.`}</p>
      ) : (
        groups.map(([state, list]) => {
          const headingId = `state-${state.replace(/\W+/g, "-")}`;
          return (
            <section key={state} aria-labelledby={headingId} className="mt-6">
              <h2 id={headingId} className="text-lg font-semibold">{state}</h2>
              <ul className="mt-1">
                {list.map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-3 border-b border-[var(--line)] py-2.5">
                    <Link href={`/station/?id=${s.id}`} className="font-medium hover:underline">{s.name}</Link>
                    <span className="flex shrink-0 items-center gap-2">
                      <span className="sr-only">{s.now.real_feel_band ? "Real Feel now:" : "Official API now:"}</span>
                      <BandPill band={s.now.real_feel_band ?? s.now.official_band} />
                      <SaveToggle id={s.id} name={s.name} />
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          );
        })
      )}
    </section>
  );
}
