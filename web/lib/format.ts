// Malaysia has no daylight saving: MYT is always UTC+8, so plain arithmetic is exact and device-independent.
const MYT_OFFSET_MS = 8 * 3600_000;

function myt(iso: string): Date {
  return new Date(Date.parse(iso) + MYT_OFFSET_MS);
}

function twelveHour(hour: number): string {
  const h = hour % 12 === 0 ? 12 : hour % 12;
  return `${h}${hour < 12 ? "am" : "pm"}`;
}

export function timeMYT(iso: string): string {
  const d = myt(iso);
  const hour = d.getUTCHours();
  const minutes = String(d.getUTCMinutes()).padStart(2, "0");
  const h = hour % 12 === 0 ? 12 : hour % 12;
  return `${h}:${minutes}${hour < 12 ? "am" : "pm"}`;
}

export function hourOfIso(iso: string): string {
  return twelveHour(myt(iso).getUTCHours());
}

export function hourLabel(hhmm: string): string {
  return twelveHour(Number(hhmm.slice(0, 2)) % 24);
}

export function weekdayDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString("en-GB", {
    weekday: "short", day: "numeric", month: "short", timeZone: "UTC",
  });
}

export function hourStart(iso: string): string {
  const t = Date.parse(iso);
  return new Date(t - (t % 3600_000)).toISOString();
}

export function isStale(iso: string, now: number = Date.now(), maxHours = 2): boolean {
  const t = Date.parse(iso);
  return Number.isNaN(t) || now - t > maxHours * 3600_000;
}

export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : `${Math.round(value * 100)}%`;
}

export function dateMYT(iso: string): string {
  return myt(iso).toISOString().slice(0, 10);
}
