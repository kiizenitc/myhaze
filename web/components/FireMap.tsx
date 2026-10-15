"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import * as maplibregl from "maplibre-gl";
import type { ExpressionSpecification, GeoJSONSource } from "maplibre-gl";
import { useEffect, useRef } from "react";

import { BANDS } from "@/lib/bands";
import { firesCollection, stationsAt } from "@/lib/geojson";
import type { Fires, MapData, WindData } from "@/lib/types";
import { fieldAt } from "@/lib/wind";

import { WindFlow } from "./windFlow";

const STYLE = "https://tiles.openfreemap.org/styles/positron";
// Copied from node_modules at build time (scripts/copy-maplibre-worker.mjs).
const WORKER_URL = "/maplibre-gl-worker.mjs";

function cssVar(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

export interface FireMapProps {
  map: MapData;
  fires?: Fires;
  wind?: WindData;
  hour: number;
  time: string;
  animate: boolean;
  onPick: (id: string) => void;
}

export function FireMap({ map, fires, wind, hour, time, animate, onPick }: FireMapProps) {
  const box = useRef<HTMLDivElement>(null);
  const instance = useRef<maplibregl.Map | null>(null);
  const flow = useRef<WindFlow | null>(null);
  const loaded = useRef(false);
  const latest = useRef({ map, fires, wind, hour, time, animate, onPick });
  useEffect(() => {
    latest.current = { map, fires, wind, hour, time, animate, onPick };
  });

  useEffect(() => {
    maplibregl.setWorkerUrl(WORKER_URL);
    const m = new maplibregl.Map({
      // Peninsular Malaysia to Sabah, fitted to whatever screen this is.
      container: box.current!, style: STYLE, bounds: [[99.6, 0.6], [119.4, 7.4]], fitBoundsOptions: { padding: 16 },
      minZoom: 3, maxZoom: 11,
      // Kept flat and north-up: the wind particles use a fast web-mercator projection that assumes it.
      dragRotate: false, pitchWithRotate: false, touchPitch: false,
      attributionControl: { compact: true },
    });
    m.touchZoomRotate.disableRotation();
    m.keyboard.disableRotation();
    instance.current = m;
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("load", () => {
      const now = latest.current;
      const colourByBand = ["match", ["get", "band"], ...BANDS.flatMap((b) => [b, cssVar(`--band-${b}`, "#9ca3af")]),
        "#9ca3af"] as unknown as ExpressionSpecification;
      m.addSource("fires", { type: "geojson", data: firesCollection(now.fires) });
      m.addLayer({ id: "fires", type: "circle", source: "fires", paint: {
        "circle-radius": ["interpolate", ["linear"], ["get", "frp"], 0, 2, 200, 4, 2000, 9],
        "circle-color": "#991b1b", "circle-opacity": 0.55 } });
      m.addSource("stations", { type: "geojson", data: stationsAt(now.map, now.hour) });
      m.addLayer({ id: "stations", type: "circle", source: "stations", paint: {
        "circle-radius": 8, "circle-color": colourByBand, "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 } });
      m.on("click", "stations", (e) => {
        const id = e.features?.[0]?.properties?.id;
        if (typeof id === "string") latest.current.onPick(id);
      });
      m.on("mouseenter", "stations", () => { m.getCanvas().style.cursor = "pointer"; });
      m.on("mouseleave", "stations", () => { m.getCanvas().style.cursor = ""; });
      const canvas = document.createElement("canvas");
      canvas.setAttribute("aria-hidden", "true");
      canvas.style.cssText = "position:absolute;inset:0;pointer-events:none";
      m.getCanvasContainer().appendChild(canvas);
      flow.current = new WindFlow(m, canvas);
      flow.current.setAnimate(now.animate);
      if (now.wind) flow.current.setField(now.wind.grid, fieldAt(now.wind, now.time));
      loaded.current = true;
    });
    return () => {
      loaded.current = false;
      flow.current?.destroy();
      flow.current = null;
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
  useEffect(() => {
    if (wind) flow.current?.setField(wind.grid, fieldAt(wind, time));
  }, [wind, time]);
  useEffect(() => {
    flow.current?.setAnimate(animate);
  }, [animate]);
  useEffect(() => {
    // No animation while the map is scrolled out of view.
    if (!box.current || typeof IntersectionObserver !== "function") return;
    const observer = new IntersectionObserver(([entry]) => flow.current?.setVisible(entry.isIntersecting));
    observer.observe(box.current);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={box} role="region" aria-label="Map of stations, fires and wind"
         className="h-[62vh] min-h-[360px] w-full overflow-hidden rounded-2xl border border-[var(--line)]" />
  );
}
