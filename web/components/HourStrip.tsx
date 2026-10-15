import { BAND_LABEL, BANDS, type Band } from "@/lib/bands";
import { hourOfIso } from "@/lib/format";

export function HourStrip({ bands, start }: { bands: Band[]; start: string }) {
  const t0 = Date.parse(start);
  const at = (h: number) => new Date(t0 + h * 3600_000).toISOString();
  const present = BANDS.filter((b) => bands.includes(b));
  return (
    <figure aria-label="Next 24 hours, Real Feel">
      <div className="flex h-6 gap-[2px] overflow-hidden rounded">
        {bands.map((band, h) => (
          <span key={h} role="img" aria-label={`${hourOfIso(at(h))}: ${BAND_LABEL[band]}`}
                title={`${hourOfIso(at(h))}: ${BAND_LABEL[band]}`} className="flex-1"
                style={{ background: `var(--band-${band})` }} />
        ))}
      </div>
      <div className="mt-1 flex text-xs text-[var(--ink-2)]">
        {[0, 6, 12, 18].map((h) => <span key={h} className="flex-1">{hourOfIso(at(h))}</span>)}
      </div>
      <figcaption className="mt-1 flex flex-wrap gap-x-3 text-xs">
        {present.map((b) => (
          <span key={b} className="inline-flex items-center gap-1">
            <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: `var(--band-${b})` }} />
            {BAND_LABEL[b]}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
