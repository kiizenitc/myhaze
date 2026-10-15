import type { Map as MapLibreMap } from "maplibre-gl";

import type { WindGrid } from "@/lib/types";
import { advect, type Field, projector, sample, secondsPerFrame } from "@/lib/wind";

const COLOUR = "rgba(15, 23, 42, 0.55)"; // dark slate: the Positron basemap is light in both themes
const FADE = 0.92; // share of each trail kept from one frame to the next
const MAX_PARTICLES = 3000;
const PIXELS_PER_PARTICLE = 150;

interface Particle {
  lon: number;
  lat: number;
  age: number;
  life: number;
}

/** Animated wind particles drawn on a canvas over the map, moving with the wind field (IQAir/earth style). */
export class WindFlow {
  private readonly map: MapLibreMap;
  private readonly canvas: HTMLCanvasElement;
  private readonly ctx: CanvasRenderingContext2D;
  private readonly still: boolean;
  private particles: Particle[] = [];
  private grid: WindGrid | null = null;
  private field: Field | null = null;
  private frame = 0;
  private moving = false;
  private width = 0;
  private height = 0;
  private seconds = 0;
  private project = projector({ lon: 0, lat: 0 }, 0, 0, 0);

  constructor(map: MapLibreMap, canvas: HTMLCanvasElement) {
    this.map = map;
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d")!;
    // People who ask their phone for less motion get one still picture of the flow instead.
    this.still = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
    map.on("movestart", this.pause);
    map.on("moveend", this.reset);
    map.on("resize", this.reset);
    this.reset();
  }

  setField(grid: WindGrid, field: Field | null): void {
    this.grid = grid;
    this.field = field;
    if (this.still) this.drawStill();
  }

  destroy(): void {
    cancelAnimationFrame(this.frame);
    this.map.off("movestart", this.pause);
    this.map.off("moveend", this.reset);
    this.map.off("resize", this.reset);
    this.canvas.remove();
  }

  private pause = (): void => {
    this.moving = true;
    cancelAnimationFrame(this.frame);
    this.ctx.clearRect(0, 0, this.width, this.height);
  };

  private reset = (): void => {
    this.moving = false;
    cancelAnimationFrame(this.frame);
    const box = this.map.getContainer();
    const dpr = window.devicePixelRatio || 1;
    this.width = box.clientWidth;
    this.height = box.clientHeight;
    this.canvas.width = Math.round(this.width * dpr);
    this.canvas.height = Math.round(this.height * dpr);
    this.canvas.style.width = `${this.width}px`;
    this.canvas.style.height = `${this.height}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const center = this.map.getCenter();
    const zoom = this.map.getZoom();
    this.project = projector({ lon: center.lng, lat: center.lat }, zoom, this.width, this.height);
    this.seconds = secondsPerFrame(zoom);
    const count = Math.min(MAX_PARTICLES, Math.round((this.width * this.height) / PIXELS_PER_PARTICLE));
    this.particles = Array.from({ length: count }, () => this.spawn(true));
    this.ctx.clearRect(0, 0, this.width, this.height);
    if (this.still) this.drawStill();
    else this.frame = requestAnimationFrame(this.tick);
  };

  private spawn(randomAge = false): Particle {
    const [lon, lat] = this.project.toLngLat(Math.random() * this.width, Math.random() * this.height);
    const life = 40 + Math.random() * 60;
    return { lon, lat, age: randomAge ? Math.random() * life : 0, life };
  }

  private tick = (): void => {
    const { ctx, grid, field } = this;
    ctx.globalCompositeOperation = "destination-in";
    ctx.fillStyle = `rgba(0, 0, 0, ${FADE})`;
    ctx.fillRect(0, 0, this.width, this.height);
    ctx.globalCompositeOperation = "source-over";
    if (grid && field) {
      ctx.strokeStyle = COLOUR;
      ctx.lineWidth = 1.25;
      ctx.beginPath();
      this.particles.forEach((p, k) => {
        const wind = sample(grid, field, p.lon, p.lat);
        if (!wind || p.age++ > p.life) {
          this.particles[k] = this.spawn();
          return;
        }
        const [x0, y0] = this.project.toScreen(p.lon, p.lat);
        [p.lon, p.lat] = advect(p.lon, p.lat, wind, this.seconds);
        const [x1, y1] = this.project.toScreen(p.lon, p.lat);
        ctx.moveTo(x0, y0);
        ctx.lineTo(x1, y1);
      });
      ctx.stroke();
    }
    if (!this.moving) this.frame = requestAnimationFrame(this.tick);
  };

  private drawStill(): void {
    const { ctx, grid, field } = this;
    ctx.clearRect(0, 0, this.width, this.height);
    if (!grid || !field) return;
    ctx.strokeStyle = COLOUR;
    ctx.lineWidth = 1.25;
    ctx.beginPath();
    for (const p of this.particles.slice(0, Math.round(this.particles.length / 3))) {
      let { lon, lat } = p;
      ctx.moveTo(...this.project.toScreen(lon, lat));
      for (let step = 0; step < 10; step++) {
        const wind = sample(grid, field, lon, lat);
        if (!wind) break;
        [lon, lat] = advect(lon, lat, wind, this.seconds * 2);
        ctx.lineTo(...this.project.toScreen(lon, lat));
      }
    }
    ctx.stroke();
  }
}
