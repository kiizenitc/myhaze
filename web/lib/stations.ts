import type { StationSummary } from "./types";

function fold(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

export function filterStations(stations: StationSummary[], query: string): StationSummary[] {
  const words = fold(query).split(/\s+/).filter(Boolean);
  return stations.filter((s) => {
    const text = fold(`${s.name} ${s.state} ${s.id}`);
    return words.every((word) => text.includes(word));
  });
}

export function groupByState(stations: StationSummary[]): [string, StationSummary[]][] {
  const groups = new Map<string, StationSummary[]>();
  for (const s of stations) groups.set(s.state, [...(groups.get(s.state) ?? []), s]);
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([state, list]) => [state, [...list].sort((a, b) => a.name.localeCompare(b.name))]);
}
