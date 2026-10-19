"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { BandPill } from "@/components/BandPill";
import { StaleBanner } from "@/components/StaleBanner";
import { BANDS } from "@/lib/bands";
import { useData } from "@/lib/data";
import { dateMYT, hourOfIso, timeMYT, weekdayDate } from "@/lib/format";
import type { Fires, MapData, WindData } from "@/lib/types";

const STEP_MS = 500; // one forecast hour per half second: the 48 hours play in about 24 seconds

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
  const [playing, setPlaying] = useState(false);
  const last = data ? data.times.length - 1 : 0;
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => setHour((h) => Math.min(h + 1, last)), STEP_MS);
    return () => clearInterval(timer);
  }, [playing, last]);
  useEffect(() => {
    if (playing && hour >= last) setPlaying(false); // the time-lapse stops on the last forecast hour
  }, [playing, hour, last]);
  if (!data) {
    return error ? <p role="alert" className="py-6">We couldn&apos;t load the map data. Check your connection; the page tries again every few minutes.</p>
      : <p>Loading…</p>;
  }
  const at = Math.min(hour, data.times.length - 1);
  const time = data.times[at];
  const when = `${weekdayDate(dateMYT(time))} ${hourOfIso(time)}`;
  return (
    <section className="grid grid-cols-1 gap-3">
      <StaleBanner generatedAt={data.generated_at} />
      <h1 className="text-2xl font-semibold">Haze map</h1>
      <aside role="note" className="rounded-xl border border-[var(--line)] bg-[var(--card)] p-3 text-sm">
        <strong>Forecast, not a measurement.</strong> At &ldquo;Now&rdquo; the dots show the latest hourly readings
        (estimated where a station has no hourly feed); every later hour is MYHaze&apos;s forecast and can be wrong.{" "}
        <Link href="/about/#how" className="text-[var(--accent)] underline">How the forecast works</Link>
        {" · "}
        <Link href="/accuracy/" className="text-[var(--accent)] underline">How accurate it is</Link>
      </aside>
      <p className="text-[var(--ink-2)]">
        Each dot is a DOE station showing its Real Feel number and band; tap one for its hour-by-hour forecast
        (crowded numbers appear as you zoom in). Small dark-red dots are fires seen by satellite on the latest
        full day.
      </p>
      <FireMap map={data} fires={fires} wind={wind} hour={at} time={time} animate={animate}
               onPick={(id) => router.push(`/station/?id=${id}`)} />
      <div className="flex items-center justify-between gap-3 text-sm">
        <p className="text-[var(--ink-2)]">
          {wind ? `Lines show the wind that carries the smoke (about 120 m up) at ${when}.`
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
        <div className="flex items-center justify-between gap-3">
          <p>
            <label htmlFor="map-hour" className="font-medium">Time</label>{" "}
            <output htmlFor="map-hour">{`${at === 0 ? "Now" : "Forecast"} · ${when}`}</output>
          </p>
          <button type="button" aria-label={playing ? "Stop the time-lapse" : "Play the 48-hour forecast"}
                  onClick={() => {
                    if (playing) {
                      setPlaying(false);
                    } else {
                      if (at >= last) setHour(0); // at the end: play again from now
                      setPlaying(true);
                    }
                  }}
                  className="shrink-0 rounded-full bg-[var(--accent)] px-4 py-1.5 font-semibold text-[var(--page)]">
            {playing ? "■ Stop" : "▶ Play"}
          </button>
        </div>
        <p className="text-xs text-[var(--ink-2)]">
          {`Latest readings: ${hourOfIso(data.times[0])} (updated ${timeMYT(data.generated_at)})`}
        </p>
        <input id="map-hour" type="range" min={0} max={last} step={1} value={at}
               onChange={(e) => {
                 setPlaying(false); // dragging the slider takes over from the time-lapse
                 setHour(Number(e.target.value));
               }} className="mt-1 w-full accent-[var(--accent)]" />
        <div className="flex justify-between text-xs text-[var(--ink-2)]"><span>Now</span><span>+24h</span><span>+48h</span></div>
      </div>
      <div className="flex flex-wrap gap-2" aria-label="Legend">{BANDS.map((b) => <BandPill key={b} band={b} />)}</div>
      <p className="text-sm"><Link href="/stations/" className="underline">Prefer a list? Choose stations from the list</Link></p>
    </section>
  );
}
