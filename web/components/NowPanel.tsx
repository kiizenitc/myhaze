import { adviceFor } from "@/lib/bands";
import { timeMYT } from "@/lib/format";
import type { Now } from "@/lib/types";

import { BandPill } from "./BandPill";

export function NowPanel({ now, sensitive }: { now: Now; sensitive: boolean }) {
  const adviceBand = now.real_feel_band ?? now.official_band;
  return (
    <section aria-label="Air now" className="grid gap-4 sm:grid-cols-2">
      <div>
        <h3 className="text-sm text-[var(--ink-2)]">Real Feel · this hour&apos;s air</h3>
        {now.real_feel !== null ? (
          <>
            <p className="flex items-center gap-3">
              <span className="text-5xl font-bold tabular-nums">{now.real_feel}</span>
              <BandPill band={now.real_feel_band} />
            </p>
            <p className="text-sm text-[var(--ink-2)]">
              PM2.5 {now.pm25} µg/m³{now.real_feel_hour ? ` at ${timeMYT(now.real_feel_hour)}` : ""}
            </p>
          </>
        ) : (
          <p className="text-[var(--ink-2)]">No hourly reading at this station right now.</p>
        )}
      </div>
      <div>
        <h3 className="text-sm text-[var(--ink-2)]">Official DOE API · 24-hour average</h3>
        {now.official_api !== null ? (
          <p className="flex items-center gap-3">
            <span className="text-3xl font-semibold tabular-nums">{now.official_api}</span>
            <BandPill band={now.official_band} />
          </p>
        ) : (
          <p className="text-[var(--ink-2)]">DOE has not published a reading in the last few hours.</p>
        )}
      </div>
      {adviceBand && <p className="sm:col-span-2">{adviceFor(adviceBand, sensitive)}</p>}
    </section>
  );
}
