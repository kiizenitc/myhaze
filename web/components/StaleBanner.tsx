import { dateMYT, isStale, timeMYT, weekdayDate } from "@/lib/format";

export function StaleBanner({ generatedAt, now = Date.now() }: { generatedAt: string; now?: number }) {
  if (!isStale(generatedAt, now)) return null;
  const known = !Number.isNaN(Date.parse(generatedAt));
  return (
    <p role="status" className="mb-4 rounded-lg border-2 border-[var(--band-unhealthy)] bg-[var(--card)] p-3">
      {"Data delayed."}
      {known ? ` Last updated ${weekdayDate(dateMYT(generatedAt))} at ${timeMYT(generatedAt)}.` : ""}
      {" Readings and forecasts may be out of date."}
    </p>
  );
}
