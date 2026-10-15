import Link from "next/link";

import { hourStart, updatedLabel } from "@/lib/format";
import type { StationSummary } from "@/lib/types";

import { ClosureNote } from "./ClosureNote";
import { HourStrip } from "./HourStrip";
import { NowPanel } from "./NowPanel";

export function StationCard({ station, generatedAt, sensitive }:
  { station: StationSummary; generatedAt: string; sensitive: boolean }) {
  const href = `/station/?id=${station.id}`;
  return (
    <article aria-labelledby={`card-${station.id}`} className="rounded-2xl border border-[var(--line)] bg-[var(--card)] p-4">
      <header className="mb-3 flex items-baseline justify-between gap-2">
        <h2 id={`card-${station.id}`} className="text-lg font-semibold">
          <Link href={href} className="hover:underline">{station.name}</Link>
        </h2>
        <span className="text-sm text-[var(--ink-2)]">{station.state}</span>
      </header>
      <NowPanel now={station.now} sensitive={sensitive} />
      <div className="mt-4"><HourStrip bands={station.next24} start={hourStart(generatedAt)} /></div>
      <div className="mt-4"><ClosureNote closure={station.closure} compact /></div>
      <footer className="mt-3 flex items-center justify-between text-sm text-[var(--ink-2)]">
        <span>{updatedLabel(generatedAt)}</span>
        <Link href={href} className="font-medium text-[var(--accent)]">Plan the day →</Link>
      </footer>
    </article>
  );
}
