"use client";

import { useState } from "react";

import { BAND_LABEL } from "@/lib/bands";
import { hourLabel, weekdayDate } from "@/lib/format";
import type { Block, Day } from "@/lib/types";

import { BandPill } from "./BandPill";

function BlockRow({ block }: { block: Block }) {
  return (
    <li className="flex items-center justify-between gap-3 border-b border-[var(--line)] py-3 last:border-0">
      <span className="font-medium tabular-nums">{`${hourLabel(block.start)}–${hourLabel(block.end)}`}</span>
      {block.status === "forecast" && block.band ? (
        <span className="flex items-center gap-2 text-sm">
          <BandPill band={block.band} />
          {block.worst_hour && <span className="text-[var(--ink-2)]">{`worst ~${hourLabel(block.worst_hour)}`}</span>}
        </span>
      ) : (
        <span className="text-sm text-[var(--ink-2)]">
          {block.status === "past" ? "Already passed" : "Beyond the 48-hour forecast"}
        </span>
      )}
    </li>
  );
}

export function DayPlan({ days, onShowHours }: { days: Day[]; onShowHours?: () => void }) {
  const [selected, setSelected] = useState(() => Math.max(0, days.findIndex((d) => d.label === "tomorrow")));
  const day = days[selected];
  return (
    <section aria-labelledby="plan-heading">
      <h2 id="plan-heading" className="text-lg font-semibold">Plan the day</h2>
      <div role="tablist" aria-label="Day" className="mt-2 flex gap-2">
        {days.map((d, i) => (
          <button key={d.date} type="button" role="tab" aria-selected={i === selected} onClick={() => setSelected(i)}
                  className={`rounded-full border px-3 py-1.5 text-sm font-semibold ${i === selected
                    ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--page)]" : "border-[var(--line)]"}`}>
            {weekdayDate(d.date)}
          </button>
        ))}
      </div>
      <div role="tabpanel" aria-label={weekdayDate(day.date)} className="mt-2">
        <ul>{day.blocks.map((b) => <BlockRow key={b.start} block={b} />)}</ul>
        <p className="mt-3">
          {day.best_window ? (
            <>
              {"Best window outdoors: "}
              <strong>{`${hourLabel(day.best_window.start)}–${hourLabel(day.best_window.end)}`}</strong>
              {` (${BAND_LABEL[day.best_window.band]})`}
            </>
          ) : "No clear stretch of good or moderate air between 7am and 7pm."}
        </p>
        <p className="mt-1 text-sm text-[var(--ink-2)]">
          Each block shows its worst likely hour. The 12am–6am block is the night after {weekdayDate(day.date)}.
        </p>
        <button type="button" onClick={onShowHours} className="mt-3 font-medium text-[var(--accent)] underline">
          See hour-by-hour forecast
        </button>
      </div>
    </section>
  );
}
