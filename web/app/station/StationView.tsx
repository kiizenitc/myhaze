"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ClosureNote } from "@/components/ClosureNote";
import { DayPlan } from "@/components/DayPlan";
import { HourlyChart } from "@/components/HourlyChart";
import { NowPanel } from "@/components/NowPanel";
import { SaveToggle } from "@/components/SaveToggle";
import { SensitiveSwitch } from "@/components/SensitiveSwitch";
import { StaleBanner } from "@/components/StaleBanner";
import { WhyList } from "@/components/WhyList";
import { useData } from "@/lib/data";
import { dateMYT, hourOfIso, timeMYT, weekdayDate } from "@/lib/format";
import { loadSensitive, saveSensitive } from "@/lib/saved";
import type { Hour, StationDetail } from "@/lib/types";

// The id comes from the URL, so only DOE-style ids are ever turned into a fetch path.
export const STATION_ID = /^[A-Z0-9]{3,12}$/;
const CARD = "rounded-2xl border border-[var(--line)] bg-[var(--card)] p-4";

function officialPeak(hours: Hour[]): Hour | null {
  return hours.reduce<Hour | null>(
    (best, h) => (h.official_api !== null && (best === null || h.official_api > (best.official_api ?? -1)) ? h : best),
    null,
  );
}

function outlook(peak: Hour | null): string {
  if (!peak || peak.official_api === null) return "No official API forecast is available for this station.";
  const range = peak.official_low !== null && peak.official_high !== null && peak.official_high > peak.official_low
    ? ` (likely ${peak.official_low}–${peak.official_high})` : "";
  return `Highest 24-hour average expected in the next 48 hours: about ${peak.official_api} around `
    + `${weekdayDate(dateMYT(peak.t))} ${hourOfIso(peak.t)}${range}.`;
}

export function StationView() {
  const raw = useSearchParams().get("id") ?? "";
  const id = STATION_ID.test(raw) ? raw : null;
  const { data, error } = useData<StationDetail>(id ? `/data/stations/${id}.json` : null);
  const [sensitive, setSensitive] = useState(false);
  const [showHours, setShowHours] = useState(false);
  useEffect(() => setSensitive(loadSensitive()), []);
  useEffect(() => {
    if (showHours) document.getElementById("hourly")?.scrollIntoView?.({ behavior: "smooth" });
  }, [showHours]);

  if (!id || (!data && error === "HTTP 404")) {
    return (
      <section className="py-10 text-center">
        <h1 className="text-2xl font-semibold">Station not found</h1>
        <p className="mt-2"><Link href="/stations/" className="text-[var(--accent)] underline">Choose from the list of stations</Link></p>
      </section>
    );
  }
  if (!data) {
    return error ? (
      <p role="alert" className="py-6">We couldn&apos;t load this station. Check your connection; the page tries again every few minutes.</p>
    ) : (
      <p>Loading…</p>
    );
  }
  return (
    <article className="grid gap-4">
      <StaleBanner generatedAt={data.generated_at} />
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">{data.name}</h1>
          <p className="text-[var(--ink-2)]">{`${data.state} · Updated ${timeMYT(data.generated_at)}`}</p>
        </div>
        <SaveToggle id={data.id} name={data.name} />
      </header>
      <div className={CARD}>
        <NowPanel now={data.now} sensitive={sensitive} />
        <div className="mt-4">
          <SensitiveSwitch checked={sensitive} onChange={(value) => { saveSensitive(value); setSensitive(value); }} />
        </div>
      </div>
      <div className={CARD}>
        <DayPlan days={data.days} onShowHours={() => {
          setShowHours(true);
          document.getElementById("hourly")?.scrollIntoView?.({ behavior: "smooth" });
        }} />
      </div>
      <div className={CARD}><WhyList why={data.why} estimated={data.estimated} /></div>
      <div className={CARD}>
        <h2 className="text-lg font-semibold">Official API outlook</h2>
        <p className="mt-1">{outlook(officialPeak(data.hours))}</p>
        <div className="mt-3"><ClosureNote closure={data.closure} /></div>
      </div>
      {showHours && (
        <section id="hourly" className={CARD} aria-labelledby="hourly-heading">
          <h2 id="hourly-heading" className="text-lg font-semibold">Hour by hour, next 48 hours</h2>
          <HourlyChart hours={data.hours} />
        </section>
      )}
    </article>
  );
}
