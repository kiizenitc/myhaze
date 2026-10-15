import type { Map as MapLibreMap } from "maplibre-gl";
import { expect, test, vi } from "vitest";

import { WindFlow } from "./windFlow";

const GRID = { lon0: 95, lat0: -7, dlon: 1, dlat: 1, nx: 27, ny: 17 };
const BREEZE = { u: Array<number>(27 * 17).fill(2), v: Array<number>(27 * 17).fill(1) };

type Handler = (...args: unknown[]) => void;

function fakeMap() {
  const handlers = new Map<string, Handler>();
  return {
    handlers,
    on: (event: string, fn: Handler) => handlers.set(event, fn),
    off: (event: string, fn: Handler) => {
      if (handlers.get(event) === fn) handlers.delete(event);
    },
    getContainer: () => ({ clientWidth: 340, clientHeight: 500 }),
    getCenter: () => ({ lng: 110, lat: 4 }),
    getZoom: () => 4,
  };
}

function fakeCanvas() {
  // jsdom has no 2D canvas: any drawing call is accepted and ignored.
  const ctx = new Proxy({} as Record<string | symbol, unknown>, {
    get: (target, key) => (key in target ? target[key] : () => undefined),
    set: (target, key, value) => {
      target[key] = value;
      return true;
    },
  });
  return { getContext: () => ctx, style: {}, width: 0, height: 0, remove: vi.fn() };
}

function animationFrames() {
  const raf = vi.fn(() => 7);
  const caf = vi.fn();
  vi.stubGlobal("requestAnimationFrame", raf);
  vi.stubGlobal("cancelAnimationFrame", caf);
  return { raf, caf };
}

const make = (map = fakeMap(), canvas = fakeCanvas()) =>
  new WindFlow(map as unknown as MapLibreMap, canvas as unknown as HTMLCanvasElement);

test("without a wind field nothing animates; with one it does; paused or off-screen it stops", () => {
  const { raf, caf } = animationFrames();
  const flow = make();
  expect(raf).not.toHaveBeenCalled();
  flow.setField(GRID, BREEZE);
  expect(raf).toHaveBeenCalledTimes(1);
  flow.setAnimate(false);
  expect(caf).toHaveBeenLastCalledWith(7);
  raf.mockClear();
  flow.setAnimate(true);
  expect(raf).toHaveBeenCalledTimes(1);
  flow.setVisible(false);
  expect(caf).toHaveBeenCalledTimes(2);
});

test("destroy stops the animation and lets go of the map", () => {
  const { caf } = animationFrames();
  const map = fakeMap();
  const canvas = fakeCanvas();
  const flow = make(map, canvas);
  flow.setField(GRID, BREEZE);
  flow.destroy();
  expect(caf).toHaveBeenCalledWith(7);
  expect(map.handlers.size).toBe(0);
  expect(canvas.remove).toHaveBeenCalled();
});

test("the overlay is capped at twice the CSS pixels on high-density phones", () => {
  animationFrames();
  vi.stubGlobal("devicePixelRatio", 3);
  const canvas = fakeCanvas();
  make(fakeMap(), canvas);
  expect(canvas.width).toBe(680);
  expect(canvas.height).toBe(1000);
});
