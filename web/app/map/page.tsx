"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useState } from "react";

import { BandPill } from "@/components/BandPill";
import { SaveToggle } from "@/components/SaveToggle";
import { BANDS } from "@/lib/bands";
import { useData } from "@/lib/data";
import { dateMYT, hourOfIso, weekdayDate } from "@/lib/format";
import type { Fires, MapData } from "@/lib/types";

// MapLibre is large and needs the browser: it loads only on this page, only on the client.
const FireMap = dynamic(() => import("@/components/FireMap").then((m) => m.FireMap), {
  ssr: false,
  loading: () => <div className="h-[62vh] min-h-[360px] rounded-2xl border border-[var(--line)] p-4">Loading map…</div>,
});

export default function MapPage() {
  const { data, error } = useData<MapData>("/data/map.json");
  const { data: fires } = useData<Fires>("/data/fires.json");
  const [hour, setHour] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  if (!data) {
    return error ? <p role="alert" className="py-6">We couldn&apos;t load the map data. Check your connection; the page tries again every few minutes.</p>
      : <p>Loading…</p>;
  }
  const at = Math.min(hour, data.times.length - 1);
  const time = data.times[at];
  const station = data.stations.find((s) => s.id === picked);
  return (
    <section className="grid gap-3">
      <h1 className="text-2xl font-semibold">Map</h1>
      <p className="text-[var(--ink-2)]">
        Station dots show the forecast Real Feel. Small dark-red dots are fires seen by satellite on the latest full
        day. Arrows show where the wind is blowing.
      </p>
      <FireMap map={data} fires={fires} hour={at} onPick={setPicked} />
      <div>
        <label htmlFor="map-hour" className="font-medium">Time</label>{" "}
        <output htmlFor="map-hour">{`${weekdayDate(dateMYT(time))} ${hourOfIso(time)}`}</output>
        <input id="map-hour" type="range" min={0} max={data.times.length - 1} step={1} value={at}
               onChange={(e) => setHour(Number(e.target.value))} className="mt-1 w-full accent-[var(--accent)]" />
        <div className="flex justify-between text-xs text-[var(--ink-2)]"><span>Now</span><span>+24h</span><span>+48h</span></div>
      </div>
      <div className="flex flex-wrap gap-2" aria-label="Legend">{BANDS.map((b) => <BandPill key={b} band={b} />)}</div>
      {station && (
        <div aria-live="polite" className="rounded-2xl border border-[var(--line)] bg-[var(--card)] p-4">
          <p className="font-semibold">{`${station.name}, ${station.state}`}</p>
          <p className="mt-1 flex items-center gap-2">
            {`Forecast Real Feel at ${hourOfIso(time)}:`} <BandPill band={station.bands[at]} />
          </p>
          <p className="mt-2 flex items-center gap-4">
            <Link href={`/station/?id=${station.id}`} className="text-[var(--accent)] underline">Plan the day</Link>
            <SaveToggle id={station.id} name={station.name} />
          </p>
        </div>
      )}
      <p className="text-sm"><Link href="/stations/" className="underline">Prefer a list? Choose stations from the list</Link></p>
    </section>
  );
}
