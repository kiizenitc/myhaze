import type { Band } from "./bands";
import type { Fires, MapData } from "./types";

export interface PointFeature<P> {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: P;
}

export interface Collection<P> {
  type: "FeatureCollection";
  features: PointFeature<P>[];
}

export interface StationProps {
  id: string;
  name: string;
  band: Band;
  wind_to?: number;
  wind_kmh?: number;
}

export function stationsAt(map: MapData, hour: number): Collection<StationProps> {
  return {
    type: "FeatureCollection",
    features: map.stations.map((s) => {
      const properties: StationProps = { id: s.id, name: s.name, band: s.bands[hour] };
      const from = s.wind_from[hour];
      const kmh = s.wind_kmh[hour];
      if (from !== null && from !== undefined) properties.wind_to = (from + 180) % 360;
      if (kmh !== null && kmh !== undefined) properties.wind_kmh = kmh;
      return { type: "Feature", geometry: { type: "Point", coordinates: [s.lon, s.lat] }, properties };
    }),
  };
}

export function firesCollection(fires: Fires | undefined): Collection<{ frp: number }> {
  return {
    type: "FeatureCollection",
    features: (fires?.cells ?? []).map(([lat, lon, frp]) => ({
      type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: { frp },
    })),
  };
}
