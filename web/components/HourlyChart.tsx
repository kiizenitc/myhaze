"use client";

import { type KeyboardEvent, useState } from "react";

import { BAND_LABEL } from "@/lib/bands";
import { dateMYT, hourOfIso, weekdayDate } from "@/lib/format";
import type { Hour } from "@/lib/types";

const W = 720;
const H = 290;
const LEFT = 50;
const RIGHT = 712;
const TOP = 12;
const BASE = 196; // bottom of the API plot
const RAIN_TOP = 222;
const RAIN_BASE = 246;
const WIND_Y = 270;
const GRID = [50, 100, 200, 300, 500];
const COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"];
const ARROW = "M0,-7 L5,3 L1,1 L1,7 L-1,7 L-1,1 L-5,3 Z"; // points north before rotation

export function compass(deg: number): string {
  return COMPASS[Math.floor(((((deg % 360) + 360) % 360) + 22.5) / 45) % 8];
}

function when(iso: string): string {
  return `${weekdayDate(dateMYT(iso))} ${hourOfIso(iso)}`;
}

function windText(h: Hour): string {
  return h.wind_kmh !== null && h.wind_from !== null ? `${Math.round(h.wind_kmh)} km/h from the ${compass(h.wind_from)}` : "–";
}

export function HourlyChart({ hours }: { hours: Hour[] }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const [active, setActive] = useState<number | null>(null);
  const last = Math.max(hours.length - 1, 1);
  const peak = Math.max(100, ...hours.flatMap((h) => [h.rf_high, h.official_high ?? 0]));
  const yMax = Math.ceil(peak / 50) * 50;
  const maxRain = Math.max(5, ...hours.map((h) => h.rain_mm ?? 0));
  const x = (i: number) => LEFT + (i * (RIGHT - LEFT)) / last;
  const y = (v: number) => BASE - (Math.min(v, yMax) / yMax) * (BASE - TOP);
  const pt = (i: number, v: number) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`;

  const line = (values: (number | null)[]) => {
    let d = "";
    let pen = false;
    values.forEach((v, i) => {
      if (v === null) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${pt(i, v)}`;
      pen = true;
    });
    return d;
  };
  const range = hours.map((h, i) => `${i ? "L" : "M"}${pt(i, h.rf_high)}`).join("")
    + hours.map((_, k) => `L${pt(last - k, hours[last - k].rf_low)}`).join("") + "Z";

  const pick = (clientX: number, rect: DOMRect) => {
    if (!rect.width) return;
    const vx = ((clientX - rect.left) / rect.width) * W;
    setActive(Math.min(Math.max(Math.round(((vx - LEFT) / (RIGHT - LEFT)) * last), 0), hours.length - 1));
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowRight") setActive((a) => Math.min((a ?? -1) + 1, hours.length - 1));
    if (e.key === "ArrowLeft") setActive((a) => Math.max((a ?? 1) - 1, 0));
    if (e.key === "Escape") setActive(null);
  };
  const tip = active === null ? null : hours[active];
  const shift = active === null ? "-50%" : active < 8 ? "0%" : active > hours.length - 9 ? "-100%" : "-50%";

  return (
    <div className="mt-2">
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block h-0.5 w-5 bg-[var(--ink)]" />Real Feel (likely)</span>
        <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block h-3 w-5 bg-[var(--ink)] opacity-15" />Likely range</span>
        <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block w-5 border-t-2 border-dashed border-[var(--accent)]" />Official API (24-hour average)</span>
        <button type="button" className="ml-auto text-[var(--accent)] underline" onClick={() => setView(view === "chart" ? "table" : "chart")}>
          {view === "chart" ? "Show as table" : "Show as chart"}
        </button>
      </div>
      {view === "chart" ? (
        <>
          {/* On a phone the 48 hours scroll sideways, so the labels stay readable instead of shrinking to a few pixels. */}
          <div className="overflow-x-auto">
            <div className="relative w-full min-w-[660px]">
              <svg role="img" aria-label="Hour-by-hour forecast chart: Real Feel with its likely range, and the official API"
                   viewBox={`0 0 ${W} ${H}`} className="w-full touch-pan-x select-none" tabIndex={0}
                   onMouseMove={(e) => pick(e.clientX, e.currentTarget.getBoundingClientRect())}
                   onPointerMove={(e) => pick(e.clientX, e.currentTarget.getBoundingClientRect())}
                   onClick={(e) => pick(e.clientX, e.currentTarget.getBoundingClientRect())}
                   onMouseLeave={() => setActive(null)} onKeyDown={onKey}>
                {GRID.filter((g) => g <= yMax).map((g) => (
                  <g key={g}>
                    <line x1={LEFT} x2={RIGHT} y1={y(g)} y2={y(g)} stroke="var(--line)" />
                    <text x={LEFT - 6} y={y(g) + 4} textAnchor="end" fontSize="12" fill="var(--ink-2)">{g}</text>
                  </g>
                ))}
                <line x1={LEFT} x2={RIGHT} y1={BASE} y2={BASE} stroke="var(--ink-2)" />
                {hours.map((h, i) => hourOfIso(h.t) === "12am" ? (
                  <g key={h.t}>
                    <line x1={x(i)} x2={x(i)} y1={TOP} y2={WIND_Y + 10} stroke="var(--line)" strokeDasharray="2 3" />
                    <text x={x(i) + 4} y={TOP + 10} fontSize="12" fill="var(--ink-2)">{weekdayDate(dateMYT(h.t)).split(" ")[0]}</text>
                  </g>
                ) : null)}
                {[0, 6, 12, 18, 24, 30, 36, 42].filter((i) => i < hours.length).map((i) => (
                  <text key={i} x={x(i)} y={BASE + 14} textAnchor="middle" fontSize="12" fill="var(--ink-2)">{hourOfIso(hours[i].t)}</text>
                ))}
                <path data-series="range" d={range} fill="var(--ink)" opacity={0.12} />
                <path data-series="real-feel" d={line(hours.map((h) => h.rf))} fill="none" stroke="var(--ink)" strokeWidth={2} />
                <path data-series="official" d={line(hours.map((h) => h.official_api))} fill="none" stroke="var(--accent)"
                      strokeWidth={2} strokeDasharray="6 4" />
                <text x={LEFT - 14} y={RAIN_BASE} textAnchor="end" fontSize="12" fill="var(--ink-2)">Rain</text>
                {hours.map((h, i) => {
                  const mm = h.rain_mm ?? 0;
                  const height = (mm / maxRain) * (RAIN_BASE - RAIN_TOP);
                  return mm >= 0.1 ? <rect key={h.t} x={x(i) - 4} y={RAIN_BASE - height} width={8} height={height} rx={2}
                                           fill="var(--accent)" opacity={0.7} /> : null;
                })}
                <text x={LEFT - 14} y={WIND_Y + 4} textAnchor="end" fontSize="12" fill="var(--ink-2)">Wind</text>
                {hours.map((h, i) => i % 3 === 0 && h.wind_from !== null ? (
                  <path key={h.t} d={ARROW} fill="var(--ink-2)" transform={`translate(${x(i)},${WIND_Y}) rotate(${(h.wind_from + 180) % 360})`} />
                ) : null)}
                {active !== null && <line x1={x(active)} x2={x(active)} y1={TOP} y2={WIND_Y + 10} stroke="var(--ink)" />}
              </svg>
              {tip && active !== null && (
                <div role="tooltip" className="pointer-events-none absolute top-0 rounded-lg border border-[var(--line)] bg-[var(--card)] p-2 text-sm shadow"
                     style={{ left: `${(x(active) / W) * 100}%`, transform: `translateX(${shift})` }}>
                  <p className="font-semibold">{when(tip.t)}</p>
                  <p>{`Real Feel ${tip.rf} ${BAND_LABEL[tip.band]}`}</p>
                  <p>{`Likely ${tip.rf_low}–${tip.rf_high}`}</p>
                  <p>{`Official API ${tip.official_api ?? "–"}`}</p>
                  {(tip.rain_mm ?? 0) >= 0.1 && <p>{`Rain ${(tip.rain_mm ?? 0).toFixed(1)} mm`}</p>}
                </div>
              )}
            </div>
          </div>
          <p className="mt-1 text-xs text-[var(--ink-2)]">
            Arrows point where the wind is blowing. Times are Malaysia time. Tap the chart for an hour&apos;s numbers.
          </p>
        </>
      ) : (
        <div className="max-h-[480px] overflow-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Hour-by-hour forecast, Malaysia time</caption>
            <thead>
              <tr><th>Time</th><th>Real Feel</th><th>Likely range</th><th>Official API</th><th>Rain</th><th>Wind</th></tr>
            </thead>
            <tbody>
              {hours.map((h) => (
                <tr key={h.t} className="border-t border-[var(--line)]">
                  <td>{when(h.t)}</td>
                  <td>{`${h.rf} ${BAND_LABEL[h.band]}`}</td>
                  <td>{`${h.rf_low}–${h.rf_high}`}</td>
                  <td>{h.official_api ?? "–"}</td>
                  <td>{(h.rain_mm ?? 0) >= 0.1 ? `${(h.rain_mm ?? 0).toFixed(1)} mm` : "–"}</td>
                  <td>{windText(h)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
