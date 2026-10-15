import { percent, weekdayDate } from "@/lib/format";
import type { Closure } from "@/lib/types";

export const CLOSURE_CAPTION =
  "Based on MOE's published rules (API above 180, or above 150 for three days running). Indicator only: MOE decides. Follow official MOE announcements.";

const RULE_TEXT = {
  api_above_180: "the official API going above 180",
  three_days_above_150: "the official API staying above 150 for three days running",
} as const;

function level(p: number): string {
  return p >= 0.7 ? "Likely" : p >= 0.3 ? "Possible" : "Unlikely";
}

export function ClosureNote({ closure, compact = false }: { closure: Closure; compact?: boolean }) {
  const day = weekdayDate(closure.school_day);
  const p = closure.probability;
  return (
    <section aria-label="School closure indicator" className="text-[15px]">
      {p === null ? (
        <p>School closure rule for {day}: not enough forecast yet to say.</p>
      ) : (
        <p>
          {`School closure rule for ${day}: `}<strong>{`${level(p)} (${percent(p)})`}</strong>
          {closure.rule && !compact ? `, mainly through ${RULE_TEXT[closure.rule]}.` : "."}
        </p>
      )}
      <p className="mt-1 text-sm text-[var(--ink-2)]">{CLOSURE_CAPTION}</p>
    </section>
  );
}
