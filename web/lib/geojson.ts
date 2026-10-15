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
  rf: number;
}

export function stationsAt(map: MapData, hour: number): Collection<StationProps> {
  return {
    type: "FeatureCollection",
    features: map.stations.map((s) => ({
      type: "Feature", geometry: { type: "Point", coordinates: [s.lon, s.lat] },
      properties: { id: s.id, name: s.name, band: s.bands[hour], rf: s.rf[hour] },
    })),
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
