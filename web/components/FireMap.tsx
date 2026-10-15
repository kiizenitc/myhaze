"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import * as maplibregl from "maplibre-gl";
import type { ExpressionSpecification, GeoJSONSource } from "maplibre-gl";
import { useEffect, useRef } from "react";

import { BANDS } from "@/lib/bands";
import { firesCollection, stationsAt } from "@/lib/geojson";
import type { Fires, MapData } from "@/lib/types";

const STYLE = "https://tiles.openfreemap.org/styles/positron";

function cssVar(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function arrow(colour: string): ImageData {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 32;
  const g = canvas.getContext("2d")!;
  g.fillStyle = colour;
  g.beginPath();
  for (const [px, py] of [[16, 2], [26, 16], [19, 16], [19, 30], [13, 30], [13, 16], [6, 16]]) g.lineTo(px, py);
  g.closePath();
  g.fill();
  return g.getImageData(0, 0, 32, 32);
}

export interface FireMapProps {
  map: MapData;
  fires?: Fires;
  hour: number;
  onPick: (id: string) => void;
}

export function FireMap({ map, fires, hour, onPick }: FireMapProps) {
  const box = useRef<HTMLDivElement>(null);
  const instance = useRef<maplibregl.Map | null>(null);
  const loaded = useRef(false);
  const latest = useRef({ map, fires, hour, onPick });
  useEffect(() => {
    latest.current = { map, fires, hour, onPick };
  });

  useEffect(() => {
    const m = new maplibregl.Map({
      container: box.current!, style: STYLE, center: [108.5, 3.5], zoom: 4.4, minZoom: 3, maxZoom: 11,
      attributionControl: { compact: true },
    });
    instance.current = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      const now = latest.current;
      const colourByBand = ["match", ["get", "band"], ...BANDS.flatMap((b) => [b, cssVar(`--band-${b}`, "#9ca3af")]),
        "#9ca3af"] as unknown as ExpressionSpecification;
      m.addImage("wind-arrow", arrow(cssVar("--ink", "#111827")));
      m.addSource("fires", { type: "geojson", data: firesCollection(now.fires) });
      m.addLayer({ id: "fires", type: "circle", source: "fires", paint: {
        "circle-radius": ["interpolate", ["linear"], ["get", "frp"], 0, 2, 200, 4, 2000, 9],
        "circle-color": "#991b1b", "circle-opacity": 0.55 } });
      m.addSource("stations", { type: "geojson", data: stationsAt(now.map, now.hour) });
      m.addLayer({ id: "wind", type: "symbol", source: "stations", filter: ["has", "wind_to"], layout: {
        "icon-image": "wind-arrow", "icon-size": 0.6, "icon-rotate": ["get", "wind_to"],
        "icon-rotation-alignment": "map", "icon-offset": [0, -26], "icon-allow-overlap": true,
        "icon-ignore-placement": true } });
      m.addLayer({ id: "stations", type: "circle", source: "stations", paint: {
        "circle-radius": 8, "circle-color": colourByBand, "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });
      m.on("click", "stations", (e) => {
        const id = e.features?.[0]?.properties?.id;
        if (typeof id === "string") latest.current.onPick(id);
      });
      m.on("mouseenter", "stations", () => { m.getCanvas().style.cursor = "pointer"; });
      m.on("mouseleave", "stations", () => { m.getCanvas().style.cursor = ""; });
      loaded.current = true;
    });
    return () => {
      loaded.current = false;
      m.remove();
      instance.current = null;
    };
  }, []);

  useEffect(() => {
    if (loaded.current) (instance.current?.getSource("stations") as GeoJSONSource | undefined)?.setData(stationsAt(map, hour));
  }, [map, hour]);
  useEffect(() => {
    if (loaded.current) (instance.current?.getSource("fires") as GeoJSONSource | undefined)?.setData(firesCollection(fires));
  }, [fires]);

  return (
    <div ref={box} role="region" aria-label="Map of stations, fires and wind"
         className="h-[62vh] min-h-[360px] w-full overflow-hidden rounded-2xl border border-[var(--line)]" />
  );
}
