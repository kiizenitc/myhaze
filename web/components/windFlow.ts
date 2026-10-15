import type { Map as MapLibreMap } from "maplibre-gl";

import type { WindGrid } from "@/lib/types";
import { advect, type Field, projector, sample, secondsPerFrame, spawnBox } from "@/lib/wind";

const COLOUR = "rgba(15, 23, 42, 0.55)"; // dark slate: the Positron basemap is light in both themes
const FADE = 0.92; // share of each trail kept from one frame to the next
const MAX_PARTICLES = 3000;
const PIXELS_PER_PARTICLE = 150;
const MAX_DPR = 2; // sharper than this costs phones a lot of pixels for nothing visible

interface Particle {
  lon: number;
  lat: number;
  age: number;
  life: number;
}

/** Wind particles drawn on a canvas over the map, moving with the wind field (IQAir/earth style).
 * It animates only with a field, while visible, unpaused and not in reduced motion; otherwise it draws
 * one still picture of short streamlines with arrowheads, so the direction is never lost. */
export class WindFlow {
  private readonly map: MapLibreMap;
  private readonly canvas: HTMLCanvasElement;
  private readonly ctx: CanvasRenderingContext2D;
  private readonly motion: MediaQueryList | null;
  private reduced = false;
  private animate = true;
  private visible = true;
  private moving = false;
  private particles: Particle[] = [];
  private grid: WindGrid | null = null;
  private field: Field | null = null;
  private frame = 0;
  private width = 0;
  private height = 0;
  private seconds = 0;
  private box: [number, number, number, number] | null = null;
  private project = projector({ lon: 0, lat: 0 }, 0, 0, 0);

  constructor(map: MapLibreMap, canvas: HTMLCanvasElement) {
    this.map = map;
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d")!;
    this.motion = typeof matchMedia === "function" ? matchMedia("(prefers-reduced-motion: reduce)") : null;
    this.reduced = this.motion?.matches ?? false;
    this.motion?.addEventListener?.("change", this.onMotionSetting);
    map.on("movestart", this.pause);
    map.on("moveend", this.reset);
    map.on("resize", this.reset);
    this.reset();
  }

  setField(grid: WindGrid, field: Field | null): void {
    const newGrid = grid !== this.grid;
    this.grid = grid;
    this.field = field;
    if (newGrid) this.seed();
    this.update();
  }

  setAnimate(on: boolean): void {
    this.animate = on;
    this.update();
  }

  setVisible(on: boolean): void {
    this.visible = on;
    this.update();
  }

  destroy(): void {
    this.stop();
    this.motion?.removeEventListener?.("change", this.onMotionSetting);
    this.map.off("movestart", this.pause);
    this.map.off("moveend", this.reset);
    this.map.off("resize", this.reset);
    this.canvas.remove();
  }

  private onMotionSetting = (event: MediaQueryListEvent): void => {
    this.reduced = event.matches;
    this.update();
  };

  private get running(): boolean {
    return Boolean(this.field) && this.animate && this.visible && !this.reduced && !this.moving;
  }

  /** Start or stop the loop, or draw the still picture, to match the current state. */
  private update(): void {
    if (this.running) {
      if (!this.frame) this.frame = requestAnimationFrame(this.tick);
      return;
    }
    this.stop();
    if (!this.moving) this.drawStill();
  }

  private stop(): void {
    if (this.frame) cancelAnimationFrame(this.frame);
    this.frame = 0;
  }

  private pause = (): void => {
    this.moving = true;
    this.stop();
    this.ctx.clearRect(0, 0, this.width, this.height);
  };

  private reset = (): void => {
    this.moving = false;
    const container = this.map.getContainer();
    const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
    this.width = container.clientWidth;
    this.height = container.clientHeight;
    this.canvas.width = Math.round(this.width * dpr);
    this.canvas.height = Math.round(this.height * dpr);
    this.canvas.style.width = `${this.width}px`;
    this.canvas.style.height = `${this.height}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const center = this.map.getCenter();
    const zoom = this.map.getZoom();
    this.project = projector({ lon: center.lng, lat: center.lat }, zoom, this.width, this.height);
    this.seconds = secondsPerFrame(zoom);
    this.ctx.clearRect(0, 0, this.width, this.height);
    this.seed();
    this.update();
  };

  /** Particles only where the view and the wind grid overlap, as many as the overlap's screen area holds. */
  private seed(): void {
    const [west, north] = this.project.toLngLat(0, 0);
    const [east, south] = this.project.toLngLat(this.width, this.height);
    this.box = this.grid ? spawnBox(this.grid, [west, south, east, north]) : null;
    if (!this.box) {
      this.particles = [];
      return;
    }
    const [x0, y0] = this.project.toScreen(this.box[0], this.box[3]);
    const [x1, y1] = this.project.toScreen(this.box[2], this.box[1]);
    const count = Math.min(MAX_PARTICLES, Math.round(((x1 - x0) * (y1 - y0)) / PIXELS_PER_PARTICLE));
    this.particles = Array.from({ length: count }, () => this.spawn(true));
  }

  private spawn(randomAge = false): Particle {
    const [west, south, east, north] = this.box!;
    const life = 40 + Math.random() * 60;
    return { lon: west + Math.random() * (east - west), lat: south + Math.random() * (north - south),
             age: randomAge ? Math.random() * life : 0, life };
  }

  private tick = (): void => {
    this.frame = 0;
    const { ctx, grid, field } = this;
    ctx.globalCompositeOperation = "destination-in";
    ctx.fillStyle = `rgba(0, 0, 0, ${FADE})`;
    ctx.fillRect(0, 0, this.width, this.height);
    ctx.globalCompositeOperation = "source-over";
    if (grid && field && this.box) {
      ctx.strokeStyle = COLOUR;
      ctx.lineWidth = 1.25;
      ctx.beginPath();
      for (let k = 0; k < this.particles.length; k++) {
        const p = this.particles[k];
        const wind = sample(grid, field, p.lon, p.lat);
        if (!wind || p.age++ > p.life) {
          this.particles[k] = this.spawn();
          continue;
        }
        const [x0, y0] = this.project.toScreen(p.lon, p.lat);
        [p.lon, p.lat] = advect(p.lon, p.lat, wind, this.seconds);
        const [x1, y1] = this.project.toScreen(p.lon, p.lat);
        ctx.moveTo(x0, y0);
        ctx.lineTo(x1, y1);
      }
      ctx.stroke();
    }
    if (this.running) this.frame = requestAnimationFrame(this.tick);
  };

  /** One still picture: short streamlines, each ending in an arrowhead pointing downwind. */
  private drawStill(): void {
    const { ctx, grid, field } = this;
    ctx.clearRect(0, 0, this.width, this.height);
    if (!grid || !field) return;
    ctx.strokeStyle = COLOUR;
    ctx.lineWidth = 1.25;
    ctx.beginPath();
    for (const p of this.particles.slice(0, Math.round(this.particles.length / 3))) {
      let { lon, lat } = p;
      let [x, y] = this.project.toScreen(lon, lat);
      let [px, py] = [x, y];
      ctx.moveTo(x, y);
      for (let step = 0; step < 10; step++) {
        const wind = sample(grid, field, lon, lat);
        if (!wind) break;
        [lon, lat] = advect(lon, lat, wind, this.seconds * 2);
        [px, py] = [x, y];
        [x, y] = this.project.toScreen(lon, lat);
        ctx.lineTo(x, y);
      }
      const angle = Math.atan2(y - py, x - px);
      if (x !== px || y !== py) {
        for (const side of [-1, 1]) {
          ctx.moveTo(x, y);
          ctx.lineTo(x - 5 * Math.cos(angle + side * 0.5), y - 5 * Math.sin(angle + side * 0.5));
        }
      }
    }
    ctx.stroke();
  }
}
