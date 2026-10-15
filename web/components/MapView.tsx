"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { BandPill } from "@/components/BandPill";
import { StaleBanner } from "@/components/StaleBanner";
import { BANDS } from "@/lib/bands";
import { useData } from "@/lib/data";
import { dateMYT, hourOfIso, weekdayDate } from "@/lib/format";
import type { Fires, MapData, WindData } from "@/lib/types";

// MapLibre is large and needs the browser: it loads on the client after the page shows, never in the first load.
const FireMap = dynamic(() => import("@/components/FireMap").then((m) => m.FireMap), {
  ssr: false,
  loading: () => <div className="h-[62vh] min-h-[360px] rounded-2xl border border-[var(--line)] p-4">Loading map…</div>,
});

/** The haze map: stations with their Real Feel, fires, the flowing wind and a 48-hour time slider. */
export function MapView() {
  const router = useRouter();
  const { data, error } = useData<MapData>("/data/map.json");
  const { data: fires } = useData<Fires>("/data/fires.json");
  const { data: wind, error: windError } = useData<WindData>("/data/wind.json");
  const [hour, setHour] = useState(0);
  const [animate, setAnimate] = useState(true);
  if (!data) {
    return error ? <p role="alert" className="py-6">We couldn&apos;t load the map data. Check your connection; the page tries again every few minutes.</p>
      : <p>Loading…</p>;
  }
  const at = Math.min(hour, data.times.length - 1);
  const time = data.times[at];
  return (
    <section className="grid grid-cols-1 gap-3">
      <StaleBanner generatedAt={data.generated_at} />
      <h1 className="text-2xl font-semibold">Haze map</h1>
      <p className="text-[var(--ink-2)]">
        Each dot is a DOE station showing its Real Feel number and band; tap one for its hour-by-hour forecast
        (crowded numbers appear as you zoom in). Small dark-red dots are fires seen by satellite on the latest
        full day.
      </p>
      <FireMap map={data} fires={fires} wind={wind} hour={at} time={time} animate={animate}
               onPick={(id) => router.push(`/station/?id=${id}`)} />
      <div className="flex items-center justify-between gap-3 text-sm">
        <p className="text-[var(--ink-2)]">
          {wind ? "Lines show the wind that carries the smoke (about 120 m up)."
            : windError ? "Wind lines are not available right now." : ""}
        </p>
        {wind && (
          <button type="button" onClick={() => setAnimate(!animate)}
                  className="shrink-0 rounded-full border border-[var(--line)] px-3 py-1.5 font-semibold">
            {animate ? "Pause wind" : "Play wind"}
          </button>
        )}
      </div>
      <div>
        <label htmlFor="map-hour" className="font-medium">Time</label>{" "}
        <output htmlFor="map-hour">{`${weekdayDate(dateMYT(time))} ${hourOfIso(time)}`}</output>
        <input id="map-hour" type="range" min={0} max={data.times.length - 1} step={1} value={at}
               onChange={(e) => setHour(Number(e.target.value))} className="mt-1 w-full accent-[var(--accent)]" />
        <div className="flex justify-between text-xs text-[var(--ink-2)]"><span>Now</span><span>+24h</span><span>+48h</span></div>
      </div>
      <div className="flex flex-wrap gap-2" aria-label="Legend">{BANDS.map((b) => <BandPill key={b} band={b} />)}</div>
      <p className="text-sm"><Link href="/stations/" className="underline">Prefer a list? Choose stations from the list</Link></p>
    </section>
  );
}
