import { BAND_LABEL, type Band } from "@/lib/bands";

export function BandPill({ band }: { band: Band | null }) {
  if (!band) {
    return (
      <span className="inline-block rounded-full border border-[var(--line)] px-2.5 py-0.5 text-sm text-[var(--ink-2)]">
        No reading
      </span>
    );
  }
  return (
    <span className="inline-block rounded-full px-2.5 py-0.5 text-sm font-semibold"
          style={{ background: `var(--band-${band})`, color: `var(--on-${band})` }}>
      {BAND_LABEL[band]}
    </span>
  );
}
