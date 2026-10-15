# MYHaze Plan 3: Website — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A fast, readable, mobile-first website that shows parents each saved station's Real Feel now, the official DOE API, a 24-hour strip, a "Plan the day" view in four 6-hour blocks with the hour-by-hour forecast, the reasons, the school-closure indicator, a station list, a map of stations and fires, and an honest accuracy page. It's deployed to Cloudflare and refreshed every hour.

**Architecture:**
- **Static site.** Next.js 16 static export in `web/`.
- **Data.** Pages are client components that fetch the JSON files written by Plan 2's forecast job: `/data/latest.json`, `/data/stations/<id>.json`, `/data/fires.json`, `/data/accuracy.json`, and `/data/map.json` (added in Task 6).
- **Hourly deploy.** One GitHub workflow builds the site, runs the forecast into `web/out/data/`, and deploys to Cloudflare Workers static assets with `wrangler`.
- **No server, no database reads by visitors, no cookies.** Saved stations and the "sensitive child" switch live in `localStorage`.
- **A reliable clock.** A tiny Cloudflare Worker with a Cron Trigger starts the GitHub workflows through `workflow_dispatch` (Task 9), because GitHub's own `schedule` trigger is best-effort.

**Tech Stack:** Next.js 16, React 19, TypeScript 5.9, Tailwind CSS 4, MapLibre GL 6 with OpenFreeMap tiles, Vitest 5 with Testing Library and jsdom, Wrangler 4 (Workers static assets and a Cron Trigger Worker), Node 24.

**Spec:** `docs/superpowers/specs/2026-10-15-myhaze-design.md` (§8 website, §9 hosting, §10 credits). **Consumes:** the JSON contract in `pipeline/myhaze/publish.py` (module docstring) from Plan 2.

## Global Constraints

- **English only.** Plain words, sentence case, body text ≥16px, mobile first (360px wide), with light and dark themes following the phone's setting.
- **Every band colour is always shown with its band word.** Colours follow DOE's scheme: good blue, moderate green, unhealthy yellow, very unhealthy orange, hazardous red.
- **Real Feel** is always labelled "this hour's air". The **official DOE API** is always labelled "24-hour average". Never mix the two.
- **The closure indicator always carries the fixed caption:** "Based on MOE's published rules (API above 180, or above 150 for three days running). Indicator only: MOE decides. Follow official MOE announcements."
- **The footer on every page credits** DOE, the World Air Quality Index Project (aqicn.org), NASA FIRMS and Open-Meteo/CAMS. It also says the forecasts are estimates and that this isn't medical advice.
- **No wording tells parents what to decide.** The advice text is general guidance, and the owner reviews it before launch (Task 8).
- **Test fixtures are synthetic.** Never copy real aqicn values into the repo (aqicn's terms forbid redistributing archived data).
- **No third-party scripts, analytics or cookies.** Map tiles come from OpenFreeMap. The only network calls are to our own `/data/*` files and the tile server.
- **First load stays small.** MapLibre loads only on `/map/`.
- **AGPL-3.0.** Secrets never enter the repo.
- **GitHub Actions are pinned to SHAs:**
  - `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` # v7.0.1
  - `astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7` # v10.2.0
  - `actions/setup-node@820762786026740c76f36085b0efc47a31fe5020` # v7.0.0
  - `actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` # v7.0.1
- Commits use the repo-local noreply identity and end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Work happens on branch `plan-3-website`.

### Deliberate changes from the spec (reasons)

- **The station page is `/station/?id=CA21B`, not `/station/CA21B/`.** A static export can't create pages for station ids unknown at build time without baking data into the build. The query parameter keeps the site independent of the data and rebuild-free.
- **Cloudflare Workers static assets instead of Cloudflare Pages.** Workers static assets is Cloudflare's current recommended home for static sites. Requests for static files are free and unmetered, and direct `wrangler deploy` uploads have no monthly build limit.
- **The site is rebuilt every hour inside the forecast workflow** (spec §9 said deploy only on code changes, if possible). One workflow is simpler, a static build takes about a minute, and `wrangler` uploads only changed files.
- **Plan-the-day tabs are labelled by date ("Fri 16 Oct"), not Today/Tomorrow.** A plan-day runs 06:00–06:00, so before 6am the "today" plan-day carries yesterday's date (Plan 2 deferred minor). The tab for tomorrow's plan-day still opens first.
- **A small `map.json` feeds the map** (spec §8.1.3: a 48-hour time slider with wind arrows). `latest.json` holds only 24 bands and no wind, and fetching 68 station files would break the "about 3 requests per page" rule.
- **A Cloudflare cron dispatches the workflows** (Task 9). GitHub's `schedule` trigger fired zero times in over three hours on the new repo, while dispatched runs started within seconds. The `schedule:` lines stay as a fallback.

## Review Focus

1. **Stale or missing data.** `generated_at` over 2 hours old must show the "Data delayed" banner. A failed fetch must show a friendly message, never a blank page, and a later successful refresh must clear it. Pinned by `StaleBanner.test`, `data.test` and `page.test` (Home error state).
2. **Null fields from estimated stations:** `real_feel: null`, `pm25: null`, blocks with status `past`/`unavailable`, `best_window: null`, closure `probability: null`. Each must render a sentence, never "null", "NaN" or a crash. Pinned in `NowPanel.test`, `DayPlan.test` and `ClosureNote.test`.
3. **Malaysia time, whatever the phone's time zone.** All times display in MYT even if the phone is set elsewhere (for a parent travelling, or a CI machine in UTC). Pinned by `format.test`, which runs with `TZ=America/New_York` in the test script.
4. **`localStorage` unavailable or corrupted** (private browsing, blocked storage, edited JSON). Saving must fail quietly and the page must still work. Pinned in `saved.test`.
5. **A station id from the URL is untrusted.** Only `^[A-Z0-9]{3,12}$` ids are fetched; anything else shows "Station not found". Pinned in `station/page.test`.

---

## File structure

```
web/
  package.json, package-lock.json      scripts: dev (copies ../site-data), build, test, typecheck
  next.config.ts                       static export, trailing slashes
  tsconfig.json, postcss.config.mjs, vitest.config.mts, vitest.setup.tsx
  wrangler.jsonc                       Cloudflare Workers static assets (./out)
  public/_headers                      cache rules for /data/*
  scripts/copy-data.mjs                dev helper: ../site-data → public/data
  app/
    globals.css                        Tailwind + colour tokens (light/dark, DOE band colours)
    layout.tsx                         header nav + footer
    page.tsx                           Home: saved station cards / empty state
    station/page.tsx, StationView.tsx  one station: now, plan the day, why, closure, hourly chart (?id=)
    stations/page.tsx                  pick stations: search + grouped list + save
    map/page.tsx                       map of stations and fires (MapLibre, lazy)
    accuracy/page.tsx                  backtest + live track record
    about/page.tsx                     what the numbers mean, advice, sources, limits
  lib/
    stations.ts                        search and group-by-state for the picker
    bands.ts                           Band type, labels, advice (+ sensitive shift)
    types.ts                           the JSON contract as TypeScript types
    format.ts                          MYT times and dates, staleness, percentages
    saved.ts                           localStorage: saved stations, sensitive switch
    data.ts                            useData hook (fetch + 10-minute refresh)
    geojson.ts                         map layers from map.json / fires.json
  components/
    Footer.tsx  BandPill.tsx  NowPanel.tsx  HourStrip.tsx  ClosureNote.tsx  StaleBanner.tsx
    StationCard.tsx  DayPlan.tsx  WhyList.tsx  HourlyChart.tsx  SensitiveSwitch.tsx  SaveToggle.tsx
    FireMap.tsx
  test/fixtures.ts                     synthetic latest/station/accuracy data
  (each component and lib file has a sibling *.test.ts(x))
scheduler/                             Cloudflare Worker: cron every 5 min → GitHub workflow_dispatch
  package.json, tsconfig.json, wrangler.jsonc, src/schedule.ts (+ test), src/index.ts
pipeline/myhaze/publish.py             + map_payload (map.json); jobs/forecast.py writes it
.github/workflows/forecast.yml         + build site, forecast into web/out/data, deploy
.github/workflows/ci.yml               + web tests, typecheck, build; scheduler tests
```

All commands run from `/Users/ryanchuah/Claude Code/MYHaze` using `npm --prefix web …`. Web test suite: `npm --prefix web test`.

---

### Task 1: Scaffold the web app, tokens, layout and footer

**Files:**
- Create: `web/package.json` (via npm), `web/next.config.ts`, `web/tsconfig.json`, `web/postcss.config.mjs`, `web/vitest.config.mts`, `web/vitest.setup.tsx`, `web/app/globals.css`, `web/app/layout.tsx`, `web/app/page.tsx` (placeholder), `web/components/Footer.tsx`, `web/components/Footer.test.tsx`
- Modify: `.gitignore`

**Interfaces:**
- Produces:
  - `Footer()`.
  - CSS tokens `--page --card --ink --ink-2 --line --accent`, plus `--band-<band>` and `--on-<band>` for each band.
  - Alias `@/` meaning `web/`.
  - `vitest.setup.tsx` mocks `next/link` as a plain `<a>`.

- [ ] **Step 1: Install the toolchain**

```bash
mkdir -p "/Users/ryanchuah/Claude Code/MYHaze/web" && cd "/Users/ryanchuah/Claude Code/MYHaze/web" && npm init -y >/dev/null
npm install next@16 react@19 react-dom@19 maplibre-gl@6
npm install -D typescript@5.9 @types/react@19 @types/react-dom@19 @types/node@24 tailwindcss@4 @tailwindcss/postcss@4 postcss vitest@5 @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event wrangler@4
npm pkg set name=myhaze-web license=AGPL-3.0-only private=true --json
npm pkg set scripts.dev="node scripts/copy-data.mjs && next dev" scripts.build="next build" scripts.test="TZ=America/New_York vitest run" scripts.typecheck="tsc --noEmit"
npm pkg delete main; node -e "const p=require('./package.json');console.log(p.name,p.private,Object.keys(p.scripts))"
```

Expected: `myhaze-web true [ 'test', 'dev', 'build', 'typecheck' ]` (in any order).

- [ ] **Step 2: Write the config files**

`web/next.config.ts`:

```ts
import type { NextConfig } from "next";

const config: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default config;
```

`web/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "es2022"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules", "out"]
}
```

`web/postcss.config.mjs`:

```js
export default { plugins: { "@tailwindcss/postcss": {} } };
```

`web/vitest.config.mts`:

```ts
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.tsx"],
    include: ["**/*.test.{ts,tsx}"],
    exclude: ["node_modules", "out", ".next"],
  },
  resolve: { alias: { "@": fileURLToPath(new URL("./", import.meta.url)) } },
});
```

`web/vitest.setup.tsx`:

```tsx
import "@testing-library/jest-dom/vitest";

import type { ReactNode } from "react";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => <a href={href} {...rest}>{children}</a>,
}));

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
});
```

`web/app/globals.css`:

```css
@import "tailwindcss";

:root {
  color-scheme: light;
  --page: #f4f5f7;
  --card: #ffffff;
  --ink: #111827;
  --ink-2: #4b5563;
  --line: #e2e5ea;
  --accent: #1d4ed8;
  /* DOE's API colours, always shown with the band word. */
  --band-good: #2563eb;
  --on-good: #ffffff;
  --band-moderate: #16a34a;
  --on-moderate: #ffffff;
  --band-unhealthy: #facc15;
  --on-unhealthy: #422006;
  --band-very_unhealthy: #f97316;
  --on-very_unhealthy: #431407;
  --band-hazardous: #dc2626;
  --on-hazardous: #ffffff;
}

@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --page: #0b0f17;
    --card: #151b26;
    --ink: #f3f4f6;
    --ink-2: #aab2bf;
    --line: #2a3446;
    --accent: #93c5fd;
  }
}

html,
body {
  background: var(--page);
  color: var(--ink);
}

body {
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size: 16px;
  line-height: 1.5;
}
```

`web/app/layout.tsx`:

```tsx
import type { Metadata, Viewport } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { Footer } from "@/components/Footer";

import "./globals.css";

export const metadata: Metadata = {
  title: "MYHaze: haze Real Feel for Malaysian parents",
  description: "Hour-by-hour haze forecast for the next 48 hours at every DOE air-quality station in Malaysia.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <Link href="/" className="text-xl font-semibold">MYHaze</Link>
          <nav className="flex gap-4 text-[15px] text-[var(--ink-2)]">
            <Link href="/stations/">Stations</Link>
            <Link href="/map/">Map</Link>
            <Link href="/about/">About</Link>
          </nav>
        </header>
        <main className="mx-auto max-w-3xl px-4 pb-10">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
```

`web/app/page.tsx` (a placeholder until Task 3):

```tsx
export default function Home() {
  return <p>Loading…</p>;
}
```

Append to the repo's `.gitignore`:

```
# web
web/node_modules/
web/.next/
web/out/
web/public/data/
web/tsconfig.tsbuildinfo
```

- [ ] **Step 3: Write the failing test**

`web/components/Footer.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { Footer } from "./Footer";

test("footer credits every data source and carries the MOE and medical disclaimers", () => {
  render(<Footer />);
  expect(screen.getByText(/follow official MOE announcements/i)).toBeInTheDocument();
  expect(screen.getByText(/not medical advice/i)).toBeInTheDocument();
  const credits = screen.getByText(/Department of Environment Malaysia \(DOE\)/);
  for (const source of ["aqicn.org", "NASA FIRMS", "Open-Meteo", "CAMS"]) {
    expect(credits.textContent).toContain(source);
  }
});
```

- [ ] **Step 4: Run it to verify it fails**

Run: `npm --prefix web test 2>&1 | tail -5`
Expected: FAIL. It can't resolve `./Footer`.

- [ ] **Step 5: Write the implementation**

`web/components/Footer.tsx`:

```tsx
import Link from "next/link";

export function Footer() {
  return (
    <footer className="mx-auto max-w-3xl px-4 pb-8 text-sm text-[var(--ink-2)]">
      <p>
        Forecasts are estimates and can be wrong. School closures are decided by the Ministry of Education (MOE):
        follow official MOE announcements. This is not medical advice.
      </p>
      <p className="mt-2">
        Data: Department of Environment Malaysia (DOE); World Air Quality Index Project (aqicn.org); NASA FIRMS;
        Open-Meteo (CC BY 4.0) with Copernicus CAMS.{" "}
        <Link href="/accuracy/" className="underline">How accurate is this?</Link>
        {" · "}
        <a href="https://github.com/kiizenitc/myhaze" className="underline">Source code (AGPL-3.0)</a>
      </p>
    </footer>
  );
}
```

- [ ] **Step 6: Run the tests and a production build**

Run: `npm --prefix web test 2>&1 | tail -3 && npm --prefix web run build 2>&1 | tail -6 && ls "/Users/ryanchuah/Claude Code/MYHaze/web/out" | head`
Expected:
- 1 test passes.
- `next build` finishes and prints the route list.
- `web/out/` contains `index.html`, `404.html` and `_next/`.

If Next 16 rewrites `tsconfig.json` (for example `jsx` or `include`) during the first build, keep its changes and commit them.

- [ ] **Step 7: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add .gitignore web
git -C "/Users/ryanchuah/Claude Code/MYHaze" status --short | grep -E "node_modules|/out/|\.next/" && echo "STOP: build output staged" || true
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(web): Next.js static site scaffold, colour tokens, layout and credits footer

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Shared library (bands and advice, contract types, Malaysia-time formatting, saved settings, data hook)

**Files:**
- Create: `web/lib/bands.ts`, `web/lib/types.ts`, `web/lib/format.ts`, `web/lib/saved.ts`, `web/lib/data.ts`, `web/test/fixtures.ts`, `web/lib/bands.test.ts`, `web/lib/format.test.ts`, `web/lib/saved.test.ts`, `web/lib/data.test.tsx`

**Interfaces:**
- Produces:
  - `Band`, `BANDS`, `BAND_LABEL`, `ADVICE`, `adviceFor(band, sensitive)`. With sensitive on, advice uses the next stricter band's wording.
  - Types `Now`, `Closure`, `StationSummary`, `Latest`, `Hour`, `Block`, `Day`, `StationDetail`, `Fires`, `MethodScores`, `Accuracy`, mirroring `publish.py`.
  - Formatting helpers:
    - `timeMYT(iso)` → "9:00am"
    - `hourLabel("18:00")` → "6pm"
    - `hourOfIso(iso)` → "4pm"
    - `weekdayDate("2026-10-16")` → "Fri 16 Oct"
    - `hourStart(iso)`
    - `isStale(iso, now = Date.now(), maxHours = 2)`
    - `percent(x)` → "71%"
  - Saved settings: `loadSaved()`, `saveSaved(ids)`, `toggleSaved(id) -> string[]`, `loadSensitive()`, `saveSensitive(v)`.
  - `useData<T>(path | null, refreshMs = 600000) -> { data?: T; error?: string }`.
  - Test data: `makeLatest()`, `makeStation(id, options)`, `makeAccuracy()`.

- [ ] **Step 1: Write the failing tests and the synthetic fixtures**

`web/test/fixtures.ts`:

```ts
import type { Band } from "@/lib/bands";
import type { Accuracy, Day, Hour, Latest, StationDetail, StationSummary } from "@/lib/types";

// Synthetic values only: never paste real aqicn readings into the repo.
export const GENERATED = "2026-10-15T02:10:00Z"; // 10:10am MYT
const START = Date.parse("2026-10-15T02:00:00Z");

function bandFor(api: number): Band {
  return api <= 50 ? "good" : api <= 100 ? "moderate" : api <= 200 ? "unhealthy" : api <= 300 ? "very_unhealthy" : "hazardous";
}

export function makeHours(rf: (h: number) => number = (h) => 150 + (h % 12) * 5): Hour[] {
  return Array.from({ length: 48 }, (_, h) => {
    const value = rf(h);
    return {
      t: new Date(START + h * 3600_000).toISOString().replace(".000Z", "Z"), rf: value, rf_low: value - 20, rf_high: value + 30,
      band: bandFor(value), pm25: Math.round(value / 3), official_api: 160, official_low: 150, official_high: 175,
      rain_mm: h === 30 ? 3.2 : 0, wind_from: 225, wind_kmh: 8,
    };
  });
}

const BLOCKS_TOMORROW = [
  { start: "06:00", end: "12:00", status: "forecast", band: "very_unhealthy", worst_hour: "08:00", worst_rf: 230 },
  { start: "12:00", end: "18:00", status: "forecast", band: "moderate", worst_hour: "12:00", worst_rf: 95 },
  { start: "18:00", end: "00:00", status: "forecast", band: "unhealthy", worst_hour: "23:00", worst_rf: 160 },
  { start: "00:00", end: "06:00", status: "forecast", band: "unhealthy", worst_hour: "03:00", worst_rf: 150 },
] as const;

export function makeDays(): Day[] {
  return [
    { label: "today", date: "2026-10-15", best_window: null, blocks: [
      { start: "06:00", end: "12:00", status: "past", band: null, worst_hour: null, worst_rf: null },
      { start: "12:00", end: "18:00", status: "forecast", band: "unhealthy", worst_hour: "17:00", worst_rf: 180 },
      { start: "18:00", end: "00:00", status: "forecast", band: "unhealthy", worst_hour: "19:00", worst_rf: 170 },
      { start: "00:00", end: "06:00", status: "forecast", band: "unhealthy", worst_hour: "05:00", worst_rf: 165 },
    ] },
    { label: "tomorrow", date: "2026-10-16", blocks: BLOCKS_TOMORROW.map((b) => ({ ...b })),
      best_window: { start: "13:00", end: "17:00", band: "moderate" } },
    { label: "day_after", date: "2026-10-17", best_window: null, blocks: [
      { start: "06:00", end: "12:00", status: "forecast", band: "unhealthy", worst_hour: "08:00", worst_rf: 140 },
      { start: "12:00", end: "18:00", status: "forecast", band: "moderate", worst_hour: "12:00", worst_rf: 90 },
      { start: "18:00", end: "00:00", status: "unavailable", band: null, worst_hour: null, worst_rf: null },
      { start: "00:00", end: "06:00", status: "unavailable", band: null, worst_hour: null, worst_rf: null },
    ] },
  ];
}

export function makeStation(id = "ZZ01A", options: { estimated?: boolean; name?: string; state?: string } = {}): StationDetail {
  const estimated = options.estimated ?? false;
  return {
    id, name: options.name ?? "Testville", state: options.state ?? "Selangor", generated_at: GENERATED,
    estimated, method: "model",
    now: estimated
      ? { real_feel: null, real_feel_band: null, pm25: null, real_feel_hour: null, official_api: 140,
          official_band: "unhealthy", official_hour: "2026-10-15T02:00:00Z" }
      : { real_feel: 214, real_feel_band: "very_unhealthy", pm25: 92.1, real_feel_hour: "2026-10-15T02:00:00Z",
          official_api: 170, official_band: "unhealthy", official_hour: "2026-10-15T02:00:00Z" },
    hours: makeHours(), days: makeDays(),
    why: ["Fires upwind, mainly in Sumatra, are adding smoke.", "Rain expected tomorrow afternoon should help clear the air."],
    closure: { school_day: "2026-10-16", probability: 0.62, rule: "three_days_above_150" },
  };
}

export function summaryOf(detail: StationDetail, lat = 3.0, lon = 101.5): StationSummary {
  return { id: detail.id, name: detail.name, state: detail.state, lat, lon, estimated: detail.estimated,
           method: detail.method, now: detail.now, next24: detail.hours.slice(0, 24).map((h) => h.band),
           closure: detail.closure };
}

export function makeLatest(): Latest {
  return { generated_at: GENERATED, stations: [
    summaryOf(makeStation("ZZ01A", { name: "Testville", state: "Selangor" }), 3.0, 101.5),
    summaryOf(makeStation("ZZ02B", { name: "Sampleton", state: "Johor", estimated: true }), 1.5, 103.7),
    summaryOf(makeStation("ZZ03C", { name: "Kampung Contoh", state: "Selangor" }), 3.2, 101.6),
  ] };
}

export function makeAccuracy(): Accuracy {
  const scores = (band: number, pod: number) => ({ n: 930, band_accuracy: band, unhealthy_days: 500, pod_unhealthy: pod,
                                                  far_unhealthy: 0.1, mae_ugm3: 8.1, coverage_80: null });
  return {
    version: "20261015T0520Z",
    backtest: {
      "1": { method: "model", meets_target: false, test_from: "2026-10-01", test_to: "2026-10-15",
             model: { ...scores(0.712, 0.81), coverage_80: 0.74 }, persistence: scores(0.58, 0.782), cams: scores(0.65, 0.796) },
      "2": { method: "cams", meets_target: false, test_from: "2026-10-01", test_to: "2026-10-15",
             model: scores(0.658, 0.758), persistence: scores(0.459, 0.687), cams: scores(0.646, 0.79) },
    },
    track_record: {},
  };
}
```

`web/lib/bands.test.ts`:

```ts
import { expect, test } from "vitest";

import { ADVICE, BAND_LABEL, BANDS, adviceFor } from "./bands";

test("every band has a label and advice", () => {
  for (const band of BANDS) {
    expect(BAND_LABEL[band]).toBeTruthy();
    expect(ADVICE[band]).toBeTruthy();
  }
  expect(BAND_LABEL.very_unhealthy).toBe("Very unhealthy");
});

test("the sensitive switch uses the next stricter band's advice", () => {
  expect(adviceFor("moderate", false)).toBe(ADVICE.moderate);
  expect(adviceFor("moderate", true)).toBe(ADVICE.unhealthy);
  expect(adviceFor("hazardous", true)).toBe(ADVICE.hazardous);
});

test("advice never tells parents to keep children home", () => {
  for (const band of BANDS) expect(ADVICE[band].toLowerCase()).not.toContain("keep your child home");
});
```

`web/lib/format.test.ts`:

```ts
import { expect, test } from "vitest";

import { hourLabel, hourOfIso, hourStart, isStale, percent, timeMYT, weekdayDate } from "./format";

test("times show in Malaysia time whatever the device time zone", () => {
  // The test script runs with TZ=America/New_York.
  expect(timeMYT("2026-10-15T01:00:00Z")).toBe("9:00am");
  expect(timeMYT("2026-10-15T04:30:00Z")).toBe("12:30pm");
  expect(timeMYT("2026-10-15T16:05:00Z")).toBe("12:05am");
  expect(hourOfIso("2026-10-15T08:00:00Z")).toBe("4pm");
});

test("block hours and dates read naturally", () => {
  expect(["06:00", "12:00", "18:00", "00:00", "08:00"].map(hourLabel)).toEqual(["6am", "12pm", "6pm", "12am", "8am"]);
  expect(weekdayDate("2026-10-16")).toBe("Fri 16 Oct");
});

test("staleness and helpers", () => {
  const now = Date.parse("2026-10-15T05:00:00Z");
  expect(isStale("2026-10-15T04:00:00Z", now)).toBe(false);
  expect(isStale("2026-10-15T02:30:00Z", now)).toBe(true);
  expect(isStale("not a date", now)).toBe(true);
  expect(hourStart("2026-10-15T02:10:00Z")).toBe("2026-10-15T02:00:00.000Z");
  expect(percent(0.712)).toBe("71%");
  expect(percent(null)).toBe("–");
});
```

`web/lib/saved.test.ts`:

```ts
import { expect, test, vi } from "vitest";

import { loadSaved, loadSensitive, saveSaved, saveSensitive, toggleSaved } from "./saved";

test("saved stations round-trip, de-duplicated and in order", () => {
  saveSaved(["CA21B", "CA01R", "CA21B"]);
  expect(loadSaved()).toEqual(["CA21B", "CA01R"]);
  expect(toggleSaved("CA01R")).toEqual(["CA21B"]);
  expect(toggleSaved("CA44Q")).toEqual(["CA21B", "CA44Q"]);
});

test("corrupted or blocked storage fails quietly", () => {
  localStorage.setItem("myhaze.saved.v1", "{not json");
  expect(loadSaved()).toEqual([]);
  localStorage.setItem("myhaze.saved.v1", JSON.stringify([1, "CA21B", null]));
  expect(loadSaved()).toEqual(["CA21B"]);
  const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  expect(loadSaved()).toEqual([]);
  expect(loadSensitive()).toBe(false);
  spy.mockRestore();
  const setSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("full"); });
  expect(() => saveSaved(["CA21B"])).not.toThrow();
  expect(() => saveSensitive(true)).not.toThrow();
  setSpy.mockRestore();
});

test("sensitive switch round-trips", () => {
  expect(loadSensitive()).toBe(false);
  saveSensitive(true);
  expect(loadSensitive()).toBe(true);
});
```

`web/lib/data.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { useData } from "./data";

function Probe({ path }: { path: string | null }) {
  const { data, error } = useData<{ value: number }>(path);
  return <p>{error ? `error: ${error}` : data ? `value: ${data.value}` : "loading"}</p>;
}

test("loads JSON", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ value: 7 }), { status: 200 })));
  render(<Probe path="/data/x.json" />);
  await waitFor(() => expect(screen.getByText("value: 7")).toBeInTheDocument());
});

test("reports HTTP errors and skips a null path", async () => {
  const fetchMock = vi.fn(async () => new Response("nope", { status: 404 }));
  vi.stubGlobal("fetch", fetchMock);
  render(<Probe path="/data/missing.json" />);
  await waitFor(() => expect(screen.getByText("error: HTTP 404")).toBeInTheDocument());
  render(<Probe path={null} />);
  expect(fetchMock).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npm --prefix web test 2>&1 | tail -5`
Expected: FAIL. It can't resolve `./bands`, `./format`, `./saved` and `./data`.

- [ ] **Step 3: Write the implementation**

`web/lib/bands.ts`:

```ts
export type Band = "good" | "moderate" | "unhealthy" | "very_unhealthy" | "hazardous";

export const BANDS: Band[] = ["good", "moderate", "unhealthy", "very_unhealthy", "hazardous"];

export const BAND_LABEL: Record<Band, string> = {
  good: "Good",
  moderate: "Moderate",
  unhealthy: "Unhealthy",
  very_unhealthy: "Very unhealthy",
  hazardous: "Hazardous",
};

// General guidance adapted from public API health advisories. The owner reviews this text before launch.
export const ADVICE: Record<Band, string> = {
  good: "Air is clean. Outdoor play and sports are fine.",
  moderate: "Air is acceptable. Most children can play outside as normal; watch children with asthma for coughing.",
  unhealthy: "Keep outdoor play and sports short and easy. Children with asthma are better off indoors.",
  very_unhealthy: "Avoid outdoor play and sports. Keep windows closed when you can.",
  hazardous: "Stay indoors with windows and doors closed. Get medical help if breathing problems appear.",
};

export function adviceFor(band: Band, sensitive: boolean): string {
  const index = Math.min(BANDS.indexOf(band) + (sensitive ? 1 : 0), BANDS.length - 1);
  return ADVICE[BANDS[index]];
}
```

`web/lib/types.ts`:

```ts
import type { Band } from "./bands";

export type { Band };

export interface Now {
  real_feel: number | null;
  real_feel_band: Band | null;
  pm25: number | null;
  real_feel_hour: string | null;
  official_api: number | null;
  official_band: Band | null;
  official_hour: string | null;
}

export interface Closure {
  school_day: string;
  probability: number | null;
  rule: "api_above_180" | "three_days_above_150" | null;
}

export interface StationSummary {
  id: string;
  name: string;
  state: string;
  lat: number;
  lon: number;
  estimated: boolean;
  method: string;
  now: Now;
  next24: Band[];
  closure: Closure;
}

export interface Latest {
  generated_at: string;
  stations: StationSummary[];
}

export interface Hour {
  t: string;
  rf: number;
  rf_low: number;
  rf_high: number;
  band: Band;
  pm25: number;
  official_api: number | null;
  official_low: number | null;
  official_high: number | null;
  rain_mm: number | null;
  wind_from: number | null;
  wind_kmh: number | null;
}

export interface Block {
  start: string;
  end: string;
  status: "forecast" | "past" | "unavailable";
  band: Band | null;
  worst_hour: string | null;
  worst_rf: number | null;
}

export interface Day {
  label: "today" | "tomorrow" | "day_after";
  date: string;
  blocks: Block[];
  best_window: { start: string; end: string; band: Band } | null;
}

export interface StationDetail {
  id: string;
  name: string;
  state: string;
  generated_at: string;
  estimated: boolean;
  method: string;
  now: Now;
  hours: Hour[];
  days: Day[];
  why: string[];
  closure: Closure;
}

export interface Fires {
  generated_at: string;
  cells: [number, number, number][];
}

export interface MethodScores {
  n: number;
  band_accuracy: number | null;
  unhealthy_days: number;
  pod_unhealthy: number | null;
  far_unhealthy: number | null;
  mae_ugm3: number | null;
  coverage_80: number | null;
}

export interface LeadReport {
  method: string;
  meets_target: boolean;
  test_from: string;
  test_to: string;
  model: MethodScores;
  persistence: MethodScores;
  cams: MethodScores;
}

export interface TrackRecord {
  days: number;
  hours: number;
  band_accuracy: number | null;
  unhealthy_hours: number;
  pod_unhealthy: number | null;
}

export interface Accuracy {
  version: string | null;
  backtest: Record<string, LeadReport> | null;
  track_record: Record<string, TrackRecord>;
}
```

`web/lib/format.ts`:

```ts
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
```

`web/lib/saved.ts`:

```ts
const SAVED_KEY = "myhaze.saved.v1";
const SENSITIVE_KEY = "myhaze.sensitive.v1";

export function loadSaved(): string[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(SAVED_KEY) ?? "[]");
    return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

export function saveSaved(ids: string[]): void {
  try {
    localStorage.setItem(SAVED_KEY, JSON.stringify([...new Set(ids)]));
  } catch {
    // Storage blocked or full: the choice simply isn't remembered.
  }
}

export function toggleSaved(id: string): string[] {
  const current = loadSaved();
  const next = current.includes(id) ? current.filter((x) => x !== id) : [...current, id];
  saveSaved(next);
  return next;
}

export function loadSensitive(): boolean {
  try {
    return localStorage.getItem(SENSITIVE_KEY) === "1";
  } catch {
    return false;
  }
}

export function saveSensitive(value: boolean): void {
  try {
    localStorage.setItem(SENSITIVE_KEY, value ? "1" : "0");
  } catch {
    // Storage blocked: the switch resets on the next visit.
  }
}
```

`web/lib/data.ts`:

```ts
"use client";

import { useEffect, useState } from "react";

export function useData<T>(path: string | null, refreshMs = 600_000): { data?: T; error?: string } {
  const [state, setState] = useState<{ data?: T; error?: string }>({});
  useEffect(() => {
    if (!path) return;
    let alive = true;
    const load = () =>
      fetch(path, { cache: "no-store" })
        .then((response) => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response.json() as Promise<T>;
        })
        .then(
          (data) => alive && setState({ data }),
          (error: unknown) =>
            alive && setState((previous) => ({ data: previous.data, error: error instanceof Error ? error.message : String(error) })),
        );
    load();
    const timer = setInterval(load, refreshMs);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [path, refreshMs]);
  return state;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix web test 2>&1 | tail -4 && npm --prefix web run typecheck 2>&1 | tail -3`
Expected: all tests pass (1 + 3 + 3 + 3 + 2 = 12), and the typecheck prints nothing.

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add web
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(web): bands and advice, contract types, Malaysia-time formatting, saved settings, data hook

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 3: Home page with saved station cards

**Files:**
- Create:
  - `web/components/BandPill.tsx`, `NowPanel.tsx`, `HourStrip.tsx`, `ClosureNote.tsx`, `StaleBanner.tsx`, `StationCard.tsx`
  - tests `web/components/NowPanel.test.tsx`, `HourStrip.test.tsx`, `ClosureNote.test.tsx`, `StaleBanner.test.tsx`, `web/app/page.test.tsx`
- Modify: `web/app/page.tsx` (replace the placeholder), `web/lib/format.ts` (+ `dateMYT`), `web/lib/format.test.ts`, `web/lib/data.test.tsx`

**Interfaces:**
- Consumes: Task 2's `Band`, `BAND_LABEL`, `BANDS`, `adviceFor`, the contract types, `timeMYT`, `hourOfIso`, `weekdayDate`, `hourStart`, `isStale`, `percent`, `loadSaved`, `loadSensitive`, `useData`, and the fixtures.
- Produces:
  - `dateMYT(iso) -> "2026-10-15"` (the Malaysia calendar date of an instant).
  - `BandPill({ band: Band | null })`: the band colour always with its word; `null` shows "No reading".
  - `NowPanel({ now: Now, sensitive: boolean })`.
  - `HourStrip({ bands: Band[], start: string })`: one cell per hour from `start`, with a legend naming every band present.
  - `CLOSURE_CAPTION` (the fixed sentence) and `ClosureNote({ closure: Closure, compact?: boolean })`.
  - `StaleBanner({ generatedAt: string, now?: number })`: renders nothing when the data is fresh.
  - `StationCard({ station: StationSummary, generatedAt: string, sensitive: boolean })`.

- [ ] **Step 1: Write the failing tests**

Append to `web/lib/format.test.ts`:

```ts
import { dateMYT } from "./format";

test("the Malaysia date of an instant", () => {
  expect(dateMYT("2026-10-15T15:59:00Z")).toBe("2026-10-15");
  expect(dateMYT("2026-10-15T16:00:00Z")).toBe("2026-10-16"); // midnight in Malaysia
});
```

Append to `web/lib/data.test.tsx`:

```tsx
function Fast() {
  const { data, error } = useData<{ value: number }>("/data/x.json", 30);
  return <p>{error ? `error: ${error}` : data ? `value: ${data.value}` : "loading"}</p>;
}

test("a later successful refresh clears the error", async () => {
  let calls = 0;
  vi.stubGlobal("fetch", vi.fn(async () =>
    ++calls === 1 ? new Response("down", { status: 503 }) : new Response(JSON.stringify({ value: 9 }), { status: 200 })));
  render(<Fast />);
  await waitFor(() => expect(screen.getByText("error: HTTP 503")).toBeInTheDocument());
  await waitFor(() => expect(screen.getByText("value: 9")).toBeInTheDocument());
});
```

`web/components/NowPanel.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { ADVICE } from "@/lib/bands";
import { makeStation } from "@/test/fixtures";

import { NowPanel } from "./NowPanel";

test("Real Feel is this hour's air and the official API is a 24-hour average", () => {
  render(<NowPanel now={makeStation().now} sensitive={false} />);
  expect(screen.getByText(/this hour's air/)).toBeInTheDocument();
  expect(screen.getByText(/24-hour average/)).toBeInTheDocument();
  expect(screen.getByText("214")).toBeInTheDocument();
  expect(screen.getByText("Very unhealthy")).toBeInTheDocument();
  expect(screen.getByText(ADVICE.very_unhealthy)).toBeInTheDocument();
});

test("an estimated station explains the missing reading and never prints null", () => {
  const { container } = render(<NowPanel now={makeStation("ZZ02B", { estimated: true }).now} sensitive />);
  expect(screen.getByText(/No hourly reading/)).toBeInTheDocument();
  expect(container.textContent).not.toMatch(/null|NaN|undefined/);
  // Advice falls back to the official band (unhealthy), one band stricter for a sensitive child.
  expect(screen.getByText(ADVICE.very_unhealthy)).toBeInTheDocument();
});
```

`web/components/HourStrip.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import type { Band } from "@/lib/bands";

import { HourStrip } from "./HourStrip";

test("every hour is coloured and named, with a legend of the bands present", () => {
  const bands: Band[] = ["moderate", ...Array<Band>(23).fill("unhealthy")];
  render(<HourStrip bands={bands} start="2026-10-15T02:00:00Z" />);
  expect(screen.getAllByRole("img")).toHaveLength(24);
  expect(screen.getByRole("img", { name: "10am: Moderate" })).toBeInTheDocument();
  expect(screen.getByText("Unhealthy")).toBeInTheDocument();
  expect(screen.queryByText("Hazardous")).toBeNull();
});
```

`web/components/ClosureNote.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { CLOSURE_CAPTION, ClosureNote } from "./ClosureNote";

test("shows the chance, the rule and the fixed MOE caption", () => {
  render(<ClosureNote closure={{ school_day: "2026-10-16", probability: 0.62, rule: "three_days_above_150" }} />);
  const note = screen.getByRole("region", { name: "School closure indicator" });
  expect(note).toHaveTextContent("School closure rule for Fri 16 Oct: Possible (62%)");
  expect(note).toHaveTextContent("mainly through the official API staying above 150 for three days running.");
  expect(screen.getByText(CLOSURE_CAPTION)).toBeInTheDocument();
});

test("a missing probability reads as a sentence and keeps the caption", () => {
  const { container } = render(<ClosureNote closure={{ school_day: "2026-10-18", probability: null, rule: null }} />);
  expect(screen.getByText(/not enough forecast yet/)).toBeInTheDocument();
  expect(container.textContent).not.toMatch(/null|NaN/);
  expect(screen.getByText(CLOSURE_CAPTION)).toBeInTheDocument();
});
```

`web/components/StaleBanner.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { StaleBanner } from "./StaleBanner";

test("appears only when the data is over two hours old", () => {
  const now = Date.parse("2026-10-15T05:00:00Z");
  const { rerender } = render(<StaleBanner generatedAt="2026-10-15T04:10:00Z" now={now} />);
  expect(screen.queryByRole("status")).toBeNull();
  rerender(<StaleBanner generatedAt="2026-10-15T02:10:00Z" now={now} />);
  expect(screen.getByRole("status")).toHaveTextContent("Data delayed. Last updated Thu 15 Oct at 10:10am.");
});
```

`web/app/page.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { saveSaved } from "@/lib/saved";
import { makeLatest } from "@/test/fixtures";

import Home from "./page";

function serve(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
}

test("with nothing saved, the home page invites choosing stations", async () => {
  serve(makeLatest());
  render(<Home />);
  expect(await screen.findByRole("link", { name: "Choose your stations" })).toHaveAttribute("href", "/stations/");
});

test("saved stations show as cards, in the order they were saved", async () => {
  saveSaved(["ZZ03C", "ZZ01A"]);
  serve(makeLatest());
  render(<Home />);
  const names = await screen.findAllByRole("heading", { level: 2 });
  expect(names.map((h) => h.textContent)).toEqual(["Kampung Contoh", "Testville"]);
  expect(screen.getAllByText(/Updated 10:10am/)).toHaveLength(2);
});

test("a failed load shows a friendly message, not a blank page", async () => {
  saveSaved(["ZZ01A"]);
  vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
  render(<Home />);
  expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't load the latest readings");
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npm --prefix web test 2>&1 | tail -8`
Expected: FAIL. `dateMYT` is not exported, the new components can't be resolved, and the home page still shows the placeholder. The new `data.test.tsx` case already passes (Task 2's hook clears the error on success); it pins that behaviour for the home page.

- [ ] **Step 3: Write the implementation**

Add to `web/lib/format.ts`:

```ts
export function dateMYT(iso: string): string {
  return myt(iso).toISOString().slice(0, 10);
}
```

`web/components/BandPill.tsx`:

```tsx
import { BAND_LABEL, type Band } from "@/lib/bands";

export function BandPill({ band }: { band: Band | null }) {
  if (!band) {
    return (
      <span className="inline-block rounded-full border border-[var(--line)] px-2.5 py-0.5 text-sm text-[var(--ink-2)]">
        No reading
      </span>
    );
  }
  return (
    <span className="inline-block rounded-full px-2.5 py-0.5 text-sm font-semibold"
          style={{ background: `var(--band-${band})`, color: `var(--on-${band})` }}>
      {BAND_LABEL[band]}
    </span>
  );
}
```

`web/components/NowPanel.tsx`:

```tsx
import { adviceFor } from "@/lib/bands";
import { timeMYT } from "@/lib/format";
import type { Now } from "@/lib/types";

import { BandPill } from "./BandPill";

export function NowPanel({ now, sensitive }: { now: Now; sensitive: boolean }) {
  const adviceBand = now.real_feel_band ?? now.official_band;
  return (
    <section aria-label="Air now" className="grid gap-4 sm:grid-cols-2">
      <div>
        <h3 className="text-sm text-[var(--ink-2)]">Real Feel · this hour&apos;s air</h3>
        {now.real_feel !== null ? (
          <>
            <p className="flex items-center gap-3">
              <span className="text-5xl font-bold tabular-nums">{now.real_feel}</span>
              <BandPill band={now.real_feel_band} />
            </p>
            <p className="text-sm text-[var(--ink-2)]">
              PM2.5 {now.pm25} µg/m³{now.real_feel_hour ? ` at ${timeMYT(now.real_feel_hour)}` : ""}
            </p>
          </>
        ) : (
          <p className="text-[var(--ink-2)]">No hourly reading at this station right now.</p>
        )}
      </div>
      <div>
        <h3 className="text-sm text-[var(--ink-2)]">Official DOE API · 24-hour average</h3>
        {now.official_api !== null ? (
          <p className="flex items-center gap-3">
            <span className="text-3xl font-semibold tabular-nums">{now.official_api}</span>
            <BandPill band={now.official_band} />
          </p>
        ) : (
          <p className="text-[var(--ink-2)]">DOE has not published a reading in the last few hours.</p>
        )}
      </div>
      {adviceBand && <p className="sm:col-span-2">{adviceFor(adviceBand, sensitive)}</p>}
    </section>
  );
}
```

`web/components/HourStrip.tsx`:

```tsx
import { BAND_LABEL, BANDS, type Band } from "@/lib/bands";
import { hourOfIso } from "@/lib/format";

export function HourStrip({ bands, start }: { bands: Band[]; start: string }) {
  const t0 = Date.parse(start);
  const at = (h: number) => new Date(t0 + h * 3600_000).toISOString();
  const present = BANDS.filter((b) => bands.includes(b));
  return (
    <figure aria-label="Next 24 hours, Real Feel">
      <div className="flex h-6 gap-[2px] overflow-hidden rounded">
        {bands.map((band, h) => (
          <span key={h} role="img" aria-label={`${hourOfIso(at(h))}: ${BAND_LABEL[band]}`}
                title={`${hourOfIso(at(h))}: ${BAND_LABEL[band]}`} className="flex-1"
                style={{ background: `var(--band-${band})` }} />
        ))}
      </div>
      <div className="mt-1 flex text-xs text-[var(--ink-2)]">
        {[0, 6, 12, 18].map((h) => <span key={h} className="flex-1">{hourOfIso(at(h))}</span>)}
      </div>
      <figcaption className="mt-1 flex flex-wrap gap-x-3 text-xs">
        {present.map((b) => (
          <span key={b} className="inline-flex items-center gap-1">
            <span aria-hidden className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: `var(--band-${b})` }} />
            {BAND_LABEL[b]}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
```

`web/components/ClosureNote.tsx`:

```tsx
import { percent, weekdayDate } from "@/lib/format";
import type { Closure } from "@/lib/types";

export const CLOSURE_CAPTION =
  "Based on MOE's published rules (API above 180, or above 150 for three days running). Indicator only: MOE decides. Follow official MOE announcements.";

const RULE_TEXT = {
  api_above_180: "the official API going above 180",
  three_days_above_150: "the official API staying above 150 for three days running",
} as const;

function level(p: number): string {
  return p >= 0.7 ? "Likely" : p >= 0.3 ? "Possible" : "Unlikely";
}

export function ClosureNote({ closure, compact = false }: { closure: Closure; compact?: boolean }) {
  const day = weekdayDate(closure.school_day);
  const p = closure.probability;
  return (
    <section aria-label="School closure indicator" className="text-[15px]">
      {p === null ? (
        <p>School closure rule for {day}: not enough forecast yet to say.</p>
      ) : (
        <p>
          {`School closure rule for ${day}: `}<strong>{`${level(p)} (${percent(p)})`}</strong>
          {closure.rule && !compact ? `, mainly through ${RULE_TEXT[closure.rule]}.` : "."}
        </p>
      )}
      <p className="mt-1 text-sm text-[var(--ink-2)]">{CLOSURE_CAPTION}</p>
    </section>
  );
}
```

`web/components/StaleBanner.tsx`:

```tsx
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
```

`web/components/StationCard.tsx`:

```tsx
import Link from "next/link";

import { hourStart, timeMYT } from "@/lib/format";
import type { StationSummary } from "@/lib/types";

import { ClosureNote } from "./ClosureNote";
import { HourStrip } from "./HourStrip";
import { NowPanel } from "./NowPanel";

export function StationCard({ station, generatedAt, sensitive }:
  { station: StationSummary; generatedAt: string; sensitive: boolean }) {
  const href = `/station/?id=${station.id}`;
  return (
    <article aria-labelledby={`card-${station.id}`} className="rounded-2xl border border-[var(--line)] bg-[var(--card)] p-4">
      <header className="mb-3 flex items-baseline justify-between gap-2">
        <h2 id={`card-${station.id}`} className="text-lg font-semibold">
          <Link href={href} className="hover:underline">{station.name}</Link>
        </h2>
        <span className="text-sm text-[var(--ink-2)]">{station.state}</span>
      </header>
      <NowPanel now={station.now} sensitive={sensitive} />
      <div className="mt-4"><HourStrip bands={station.next24} start={hourStart(generatedAt)} /></div>
      <div className="mt-4"><ClosureNote closure={station.closure} compact /></div>
      <footer className="mt-3 flex items-center justify-between text-sm text-[var(--ink-2)]">
        <span>Updated {timeMYT(generatedAt)}</span>
        <Link href={href} className="font-medium text-[var(--accent)]">Plan the day →</Link>
      </footer>
    </article>
  );
}
```

`web/app/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { StaleBanner } from "@/components/StaleBanner";
import { StationCard } from "@/components/StationCard";
import { useData } from "@/lib/data";
import { loadSaved, loadSensitive } from "@/lib/saved";
import type { Latest, StationSummary } from "@/lib/types";

export default function Home() {
  const { data, error } = useData<Latest>("/data/latest.json");
  const [saved, setSaved] = useState<string[] | null>(null);
  const [sensitive, setSensitive] = useState(false);
  useEffect(() => {
    // localStorage exists only in the browser, so it is read after the first render.
    setSaved(loadSaved());
    setSensitive(loadSensitive());
  }, []);

  if (saved === null) return <p>Loading…</p>;
  if (saved.length === 0) {
    return (
      <section className="py-10 text-center">
        <h1 className="text-2xl font-semibold">Haze Real Feel for your child&apos;s day</h1>
        <p className="mt-2 text-[var(--ink-2)]">
          Pick the stations near home, school, tuition or sports to see this hour&apos;s air and the next 48 hours.
        </p>
        <Link href="/stations/" className="mt-6 inline-block rounded-full bg-[var(--accent)] px-5 py-2.5 font-semibold text-[var(--page)]">
          Choose your stations
        </Link>
      </section>
    );
  }
  if (!data) {
    return error ? (
      <p role="alert" className="py-6">
        We couldn&apos;t load the latest readings. Check your connection; the page tries again every few minutes.
      </p>
    ) : (
      <p>Loading…</p>
    );
  }
  const byId = new Map(data.stations.map((s) => [s.id, s]));
  const cards = saved.map((id) => byId.get(id)).filter((s): s is StationSummary => s !== undefined);
  return (
    <>
      <StaleBanner generatedAt={data.generated_at} />
      <div className="grid gap-4">
        {cards.map((s) => <StationCard key={s.id} station={s} generatedAt={data.generated_at} sensitive={sensitive} />)}
      </div>
      <p className="mt-6 text-center">
        <Link href="/stations/" className="text-[var(--accent)] underline">Add or remove stations</Link>
      </p>
    </>
  );
}
```

- [ ] **Step 4: Run the tests and the typecheck**

Run: `npm --prefix web test 2>&1 | tail -4 && npm --prefix web run typecheck 2>&1 | tail -3`
Expected: all tests pass (12 from Tasks 1–2 + 11 new = 23), and the typecheck prints nothing.

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add web
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(web): home page with saved station cards, Real Feel and official API, 24-hour strip, closure note

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Station page (now, plan the day, why, official outlook, hour by hour)

**Files:**
- Create:
  - `web/components/DayPlan.tsx`, `WhyList.tsx`, `HourlyChart.tsx`, `SensitiveSwitch.tsx`, `SaveToggle.tsx`
  - `web/app/station/page.tsx`, `web/app/station/StationView.tsx`
  - tests `web/components/DayPlan.test.tsx`, `WhyList.test.tsx`, `HourlyChart.test.tsx`, `web/app/station/page.test.tsx`

**Interfaces:**
- Consumes: Task 2's library and fixtures; Task 3's `BandPill`, `NowPanel`, `ClosureNote`, `CLOSURE_CAPTION`, `StaleBanner`, `dateMYT`.
- Produces:
  - `DayPlan({ days: Day[], onShowHours?: () => void })`. Tabs are labelled by date only ("Fri 16 Oct"), and the tab for the plan-day labelled `tomorrow` opens first. Before 06:00 the `today` plan-day still carries yesterday's date, so the words Today/Tomorrow would mislead (Plan 2 deferred minor).
  - `WhyList({ why: string[], estimated: boolean })`.
  - `HourlyChart({ hours: Hour[] })`: an SVG chart with a hover/keyboard tooltip, plus a table view. Also `compass(deg) -> "south-west"`.
  - `SensitiveSwitch({ checked, onChange })`, `SaveToggle({ id, name })`.
  - `STATION_ID = /^[A-Z0-9]{3,12}$/` and `StationView()` (reads `?id=`).
- Hour bands always come from the `band` field in the JSON. The site never recomputes a band from a number (Python and JavaScript round differently at the edges).

- [ ] **Step 1: Write the failing tests**

`web/components/DayPlan.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { makeDays } from "@/test/fixtures";

import { DayPlan } from "./DayPlan";

test("opens on tomorrow, with tabs labelled by date and each block's worst hour", () => {
  render(<DayPlan days={makeDays()} />);
  expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Thu 15 Oct", "Fri 16 Oct", "Sat 17 Oct"]);
  expect(screen.getByRole("tab", { selected: true })).toHaveTextContent("Fri 16 Oct");
  expect(screen.getByText("worst ~8am")).toBeInTheDocument();
  expect(screen.getByText("Very unhealthy")).toBeInTheDocument();
  expect(screen.getByText(/Best window outdoors/)).toHaveTextContent("Best window outdoors: 1pm–5pm (Moderate)");
});

test("past and unavailable blocks, and a day without a window, read as sentences", async () => {
  render(<DayPlan days={makeDays()} />);
  await userEvent.click(screen.getByRole("tab", { name: "Thu 15 Oct" }));
  expect(screen.getByText("Already passed")).toBeInTheDocument();
  expect(screen.getByText(/No clear stretch of good or moderate air/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("tab", { name: "Sat 17 Oct" }));
  expect(screen.getAllByText("Beyond the 48-hour forecast")).toHaveLength(2);
});

test("the hour-by-hour link asks for the hourly forecast", async () => {
  const onShowHours = vi.fn();
  render(<DayPlan days={makeDays()} onShowHours={onShowHours} />);
  await userEvent.click(screen.getByRole("button", { name: "See hour-by-hour forecast" }));
  expect(onShowHours).toHaveBeenCalledTimes(1);
});
```

`web/components/WhyList.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { WhyList } from "./WhyList";

test("lists the reasons", () => {
  render(<WhyList why={["Fires upwind are adding smoke.", "Rain on the way should help clear the air."]} estimated={false} />);
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
});

test("no reasons, and an estimated station, read as sentences", () => {
  render(<WhyList why={[]} estimated />);
  expect(screen.getByText(/No single strong reason/)).toBeInTheDocument();
  expect(screen.getByText(/no hourly feed right now/)).toBeInTheDocument();
});
```

`web/components/HourlyChart.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";

import { makeHours } from "@/test/fixtures";

import { HourlyChart, compass } from "./HourlyChart";

test("draws the Real Feel range, the Real Feel line and the official API line, with a legend", () => {
  render(<HourlyChart hours={makeHours()} />);
  const chart = screen.getByRole("img", { name: /Hour-by-hour forecast chart/ });
  expect(chart.querySelectorAll("path[data-series]")).toHaveLength(3);
  expect(screen.getByText("Real Feel (likely)")).toBeInTheDocument();
  expect(screen.getByText("Official API (24-hour average)")).toBeInTheDocument();
});

test("hovering shows that hour's numbers in Malaysia time", () => {
  render(<HourlyChart hours={makeHours()} />);
  const chart = screen.getByRole("img", { name: /Hour-by-hour forecast chart/ });
  chart.getBoundingClientRect = () => ({ left: 0, top: 0, width: 720, height: 290, right: 720, bottom: 290, x: 0, y: 0, toJSON: () => ({}) });
  fireEvent.mouseMove(chart, { clientX: 40, clientY: 100 }); // the first hour
  const tip = screen.getByRole("tooltip");
  expect(tip).toHaveTextContent("Thu 15 Oct 10am");
  expect(tip).toHaveTextContent("Real Feel 150 Unhealthy");
  expect(tip).toHaveTextContent("Official API 160");
});

test("the table view lists all 48 hours", async () => {
  render(<HourlyChart hours={makeHours()} />);
  await userEvent.click(screen.getByRole("button", { name: "Show as table" }));
  expect(screen.getAllByRole("row")).toHaveLength(49);
  expect(screen.getAllByText("8 km/h from the south-west").length).toBeGreaterThan(0);
});

test("compass", () => {
  expect([0, 44, 90, 225, 350, -45].map(compass)).toEqual(["north", "north-east", "east", "south-west", "north", "north-west"]);
});
```

`web/app/station/page.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { CLOSURE_CAPTION } from "@/components/ClosureNote";
import { ADVICE } from "@/lib/bands";
import { loadSaved, loadSensitive } from "@/lib/saved";
import { makeStation } from "@/test/fixtures";

import { StationView } from "./StationView";

const search = vi.hoisted(() => ({ value: "id=ZZ01A" }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(search.value) }));

beforeEach(() => {
  search.value = "id=ZZ01A";
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(makeStation("ZZ01A")), { status: 200 })));
});

test("shows now, the plan for tomorrow, the reasons, the official outlook and the closure note", async () => {
  render(<StationView />);
  expect(await screen.findByRole("heading", { level: 1, name: "Testville" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { selected: true })).toHaveTextContent("Fri 16 Oct");
  expect(screen.getByText("Fires upwind, mainly in Sumatra, are adding smoke.")).toBeInTheDocument();
  expect(screen.getByText(/Highest 24-hour average/)).toHaveTextContent("about 160 around Thu 15 Oct 10am (likely 150–175)");
  expect(screen.getByText(CLOSURE_CAPTION)).toBeInTheDocument();
});

test("the sensitive switch makes the advice one band stricter and is remembered", async () => {
  render(<StationView />);
  expect(await screen.findByText(ADVICE.very_unhealthy)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("switch"));
  expect(screen.getByText(ADVICE.hazardous)).toBeInTheDocument();
  expect(loadSensitive()).toBe(true);
});

test("the hour-by-hour forecast opens from the plan", async () => {
  render(<StationView />);
  await userEvent.click(await screen.findByRole("button", { name: "See hour-by-hour forecast" }));
  expect(screen.getByRole("img", { name: /Hour-by-hour forecast chart/ })).toBeInTheDocument();
});

test("saving the station remembers it", async () => {
  render(<StationView />);
  await userEvent.click(await screen.findByRole("button", { name: /Save Testville/ }));
  expect(loadSaved()).toEqual(["ZZ01A"]);
  expect(screen.getByRole("button", { name: /Saved Testville/ })).toHaveAttribute("aria-pressed", "true");
});

test.each(["", "../latest", "zz01a", "A".repeat(13), "ZZ01A/../x"])("an untrusted id %j is never fetched", (bad) => {
  search.value = `id=${encodeURIComponent(bad)}`;
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  render(<StationView />);
  expect(screen.getByRole("heading", { name: "Station not found" })).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("an unknown station reads as not found", async () => {
  search.value = "id=ZZ99Z";
  vi.stubGlobal("fetch", vi.fn(async () => new Response("missing", { status: 404 })));
  render(<StationView />);
  expect(await screen.findByRole("heading", { name: "Station not found" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npm --prefix web test 2>&1 | tail -8`
Expected: FAIL. `./DayPlan`, `./WhyList`, `./HourlyChart` and `./StationView` can't be resolved.

- [ ] **Step 3: Write the implementation**

`web/components/DayPlan.tsx`:

```tsx
"use client";

import { useState } from "react";

import { BAND_LABEL } from "@/lib/bands";
import { hourLabel, weekdayDate } from "@/lib/format";
import type { Block, Day } from "@/lib/types";

import { BandPill } from "./BandPill";

function BlockRow({ block }: { block: Block }) {
  return (
    <li className="flex items-center justify-between gap-3 border-b border-[var(--line)] py-3 last:border-0">
      <span className="font-medium tabular-nums">{`${hourLabel(block.start)}–${hourLabel(block.end)}`}</span>
      {block.status === "forecast" && block.band ? (
        <span className="flex items-center gap-2 text-sm">
          <BandPill band={block.band} />
          {block.worst_hour && <span className="text-[var(--ink-2)]">{`worst ~${hourLabel(block.worst_hour)}`}</span>}
        </span>
      ) : (
        <span className="text-sm text-[var(--ink-2)]">
          {block.status === "past" ? "Already passed" : "Beyond the 48-hour forecast"}
        </span>
      )}
    </li>
  );
}

export function DayPlan({ days, onShowHours }: { days: Day[]; onShowHours?: () => void }) {
  const [selected, setSelected] = useState(() => Math.max(0, days.findIndex((d) => d.label === "tomorrow")));
  const day = days[selected];
  return (
    <section aria-labelledby="plan-heading">
      <h2 id="plan-heading" className="text-lg font-semibold">Plan the day</h2>
      <div role="tablist" aria-label="Day" className="mt-2 flex gap-2">
        {days.map((d, i) => (
          <button key={d.date} type="button" role="tab" aria-selected={i === selected} onClick={() => setSelected(i)}
                  className={`rounded-full border px-3 py-1.5 text-sm font-semibold ${i === selected
                    ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--page)]" : "border-[var(--line)]"}`}>
            {weekdayDate(d.date)}
          </button>
        ))}
      </div>
      <div role="tabpanel" aria-label={weekdayDate(day.date)} className="mt-2">
        <ul>{day.blocks.map((b) => <BlockRow key={b.start} block={b} />)}</ul>
        <p className="mt-3">
          {day.best_window ? (
            <>
              {"Best window outdoors: "}
              <strong>{`${hourLabel(day.best_window.start)}–${hourLabel(day.best_window.end)}`}</strong>
              {` (${BAND_LABEL[day.best_window.band]})`}
            </>
          ) : "No clear stretch of good or moderate air between 7am and 7pm."}
        </p>
        <p className="mt-1 text-sm text-[var(--ink-2)]">
          Each block shows its worst likely hour. The 12am–6am block is the night after {weekdayDate(day.date)}.
        </p>
        <button type="button" onClick={onShowHours} className="mt-3 font-medium text-[var(--accent)] underline">
          See hour-by-hour forecast
        </button>
      </div>
    </section>
  );
}
```

`web/components/WhyList.tsx`:

```tsx
export function WhyList({ why, estimated }: { why: string[]; estimated: boolean }) {
  return (
    <section aria-labelledby="why-heading">
      <h2 id="why-heading" className="text-lg font-semibold">Why</h2>
      {why.length ? (
        <ul className="mt-2 list-disc space-y-1 pl-5">{why.map((reason) => <li key={reason}>{reason}</li>)}</ul>
      ) : (
        <p className="mt-2 text-[var(--ink-2)]">No single strong reason stands out for this forecast.</p>
      )}
      {estimated && (
        <p className="mt-2 text-sm text-[var(--ink-2)]">
          This station has no hourly feed right now, so its forecast starts from the official reading or the regional
          smoke forecast and is less certain.
        </p>
      )}
    </section>
  );
}
```

`web/components/HourlyChart.tsx`:

```tsx
"use client";

import { type KeyboardEvent, useState } from "react";

import { BAND_LABEL } from "@/lib/bands";
import { dateMYT, hourOfIso, weekdayDate } from "@/lib/format";
import type { Hour } from "@/lib/types";

const W = 720;
const H = 290;
const LEFT = 40;
const RIGHT = 712;
const TOP = 12;
const BASE = 196; // bottom of the API plot
const RAIN_TOP = 222;
const RAIN_BASE = 246;
const WIND_Y = 270;
const GRID = [50, 100, 200, 300, 500];
const COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"];
const ARROW = "M0,-7 L5,3 L1,1 L1,7 L-1,7 L-1,1 L-5,3 Z"; // points north before rotation

export function compass(deg: number): string {
  return COMPASS[Math.floor(((((deg % 360) + 360) % 360) + 22.5) / 45) % 8];
}

function when(iso: string): string {
  return `${weekdayDate(dateMYT(iso))} ${hourOfIso(iso)}`;
}

function windText(h: Hour): string {
  return h.wind_kmh !== null && h.wind_from !== null ? `${Math.round(h.wind_kmh)} km/h from the ${compass(h.wind_from)}` : "–";
}

export function HourlyChart({ hours }: { hours: Hour[] }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const [active, setActive] = useState<number | null>(null);
  const last = Math.max(hours.length - 1, 1);
  const peak = Math.max(100, ...hours.flatMap((h) => [h.rf_high, h.official_high ?? 0]));
  const yMax = Math.ceil(peak / 50) * 50;
  const maxRain = Math.max(5, ...hours.map((h) => h.rain_mm ?? 0));
  const x = (i: number) => LEFT + (i * (RIGHT - LEFT)) / last;
  const y = (v: number) => BASE - (Math.min(v, yMax) / yMax) * (BASE - TOP);
  const pt = (i: number, v: number) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`;

  const line = (values: (number | null)[]) => {
    let d = "";
    let pen = false;
    values.forEach((v, i) => {
      if (v === null) {
        pen = false;
        return;
      }
      d += `${pen ? "L" : "M"}${pt(i, v)}`;
      pen = true;
    });
    return d;
  };
  const range = hours.map((h, i) => `${i ? "L" : "M"}${pt(i, h.rf_high)}`).join("")
    + hours.map((_, k) => `L${pt(last - k, hours[last - k].rf_low)}`).join("") + "Z";

  const pick = (clientX: number, rect: DOMRect) => {
    if (!rect.width) return;
    const vx = ((clientX - rect.left) / rect.width) * W;
    setActive(Math.min(Math.max(Math.round(((vx - LEFT) / (RIGHT - LEFT)) * last), 0), hours.length - 1));
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowRight") setActive((a) => Math.min((a ?? -1) + 1, hours.length - 1));
    if (e.key === "ArrowLeft") setActive((a) => Math.max((a ?? 1) - 1, 0));
    if (e.key === "Escape") setActive(null);
  };
  const tip = active === null ? null : hours[active];
  const shift = active === null ? "-50%" : active < 8 ? "0%" : active > hours.length - 9 ? "-100%" : "-50%";

  return (
    <div className="mt-2">
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block h-0.5 w-5 bg-[var(--ink)]" />Real Feel (likely)</span>
        <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block h-3 w-5 bg-[var(--ink)] opacity-15" />Likely range</span>
        <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block w-5 border-t-2 border-dashed border-[var(--accent)]" />Official API (24-hour average)</span>
        <button type="button" className="ml-auto text-[var(--accent)] underline" onClick={() => setView(view === "chart" ? "table" : "chart")}>
          {view === "chart" ? "Show as table" : "Show as chart"}
        </button>
      </div>
      {view === "chart" ? (
        <div className="relative">
          <svg role="img" aria-label="Hour-by-hour forecast chart: Real Feel with its likely range, and the official API"
               viewBox={`0 0 ${W} ${H}`} className="w-full touch-none select-none" tabIndex={0}
               onMouseMove={(e) => pick(e.clientX, e.currentTarget.getBoundingClientRect())}
               onPointerMove={(e) => pick(e.clientX, e.currentTarget.getBoundingClientRect())}
               onMouseLeave={() => setActive(null)} onKeyDown={onKey}>
            {GRID.filter((g) => g <= yMax).map((g) => (
              <g key={g}>
                <line x1={LEFT} x2={RIGHT} y1={y(g)} y2={y(g)} stroke="var(--line)" />
                <text x={LEFT - 6} y={y(g) + 4} textAnchor="end" fontSize="11" fill="var(--ink-2)">{g}</text>
              </g>
            ))}
            <line x1={LEFT} x2={RIGHT} y1={BASE} y2={BASE} stroke="var(--ink-2)" />
            {hours.map((h, i) => hourOfIso(h.t) === "12am" ? (
              <g key={h.t}>
                <line x1={x(i)} x2={x(i)} y1={TOP} y2={WIND_Y + 10} stroke="var(--line)" strokeDasharray="2 3" />
                <text x={x(i) + 4} y={TOP + 10} fontSize="11" fill="var(--ink-2)">{weekdayDate(dateMYT(h.t)).split(" ")[0]}</text>
              </g>
            ) : null)}
            {[0, 6, 12, 18, 24, 30, 36, 42].filter((i) => i < hours.length).map((i) => (
              <text key={i} x={x(i)} y={BASE + 14} textAnchor="middle" fontSize="11" fill="var(--ink-2)">{hourOfIso(hours[i].t)}</text>
            ))}
            <path data-series="range" d={range} fill="var(--ink)" opacity={0.12} />
            <path data-series="real-feel" d={line(hours.map((h) => h.rf))} fill="none" stroke="var(--ink)" strokeWidth={2} />
            <path data-series="official" d={line(hours.map((h) => h.official_api))} fill="none" stroke="var(--accent)"
                  strokeWidth={2} strokeDasharray="6 4" />
            <text x={LEFT - 6} y={RAIN_BASE} textAnchor="end" fontSize="11" fill="var(--ink-2)">Rain</text>
            {hours.map((h, i) => {
              const mm = h.rain_mm ?? 0;
              const height = (mm / maxRain) * (RAIN_BASE - RAIN_TOP);
              return mm >= 0.1 ? <rect key={h.t} x={x(i) - 4} y={RAIN_BASE - height} width={8} height={height} rx={2}
                                       fill="var(--accent)" opacity={0.7} /> : null;
            })}
            <text x={LEFT - 6} y={WIND_Y + 4} textAnchor="end" fontSize="11" fill="var(--ink-2)">Wind</text>
            {hours.map((h, i) => i % 3 === 0 && h.wind_from !== null ? (
              <path key={h.t} d={ARROW} fill="var(--ink-2)" transform={`translate(${x(i)},${WIND_Y}) rotate(${(h.wind_from + 180) % 360})`} />
            ) : null)}
            {active !== null && <line x1={x(active)} x2={x(active)} y1={TOP} y2={WIND_Y + 10} stroke="var(--ink)" />}
          </svg>
          {tip && active !== null && (
            <div role="tooltip" className="pointer-events-none absolute top-0 rounded-lg border border-[var(--line)] bg-[var(--card)] p-2 text-sm shadow"
                 style={{ left: `${(x(active) / W) * 100}%`, transform: `translateX(${shift})` }}>
              <p className="font-semibold">{when(tip.t)}</p>
              <p>{`Real Feel ${tip.rf} ${BAND_LABEL[tip.band]}`}</p>
              <p>{`Likely ${tip.rf_low}–${tip.rf_high}`}</p>
              <p>{`Official API ${tip.official_api ?? "–"}`}</p>
              {(tip.rain_mm ?? 0) >= 0.1 && <p>{`Rain ${(tip.rain_mm ?? 0).toFixed(1)} mm`}</p>}
            </div>
          )}
          <p className="mt-1 text-xs text-[var(--ink-2)]">Arrows point where the wind is blowing. Times are Malaysia time.</p>
        </div>
      ) : (
        <div className="max-h-[480px] overflow-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Hour-by-hour forecast, Malaysia time</caption>
            <thead>
              <tr><th>Time</th><th>Real Feel</th><th>Likely range</th><th>Official API</th><th>Rain</th><th>Wind</th></tr>
            </thead>
            <tbody>
              {hours.map((h) => (
                <tr key={h.t} className="border-t border-[var(--line)]">
                  <td>{when(h.t)}</td>
                  <td>{`${h.rf} ${BAND_LABEL[h.band]}`}</td>
                  <td>{`${h.rf_low}–${h.rf_high}`}</td>
                  <td>{h.official_api ?? "–"}</td>
                  <td>{(h.rain_mm ?? 0) >= 0.1 ? `${(h.rain_mm ?? 0).toFixed(1)} mm` : "–"}</td>
                  <td>{windText(h)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

`web/components/SensitiveSwitch.tsx`:

```tsx
"use client";

export function SensitiveSwitch({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex items-start gap-3">
      <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)}
             className="mt-1 h-5 w-5 accent-[var(--accent)]" />
      <span>My child is sensitive (asthma or other breathing problems): show advice one band earlier</span>
    </label>
  );
}
```

`web/components/SaveToggle.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";

import { loadSaved, toggleSaved } from "@/lib/saved";

export function SaveToggle({ id, name }: { id: string; name: string }) {
  const [saved, setSaved] = useState(false);
  useEffect(() => setSaved(loadSaved().includes(id)), [id]);
  return (
    <button type="button" aria-pressed={saved} onClick={() => setSaved(toggleSaved(id).includes(id))}
            className={`rounded-full border px-3 py-1.5 text-sm font-semibold ${saved
              ? "border-[var(--accent)] text-[var(--accent)]" : "border-[var(--line)]"}`}>
      {saved ? "★ Saved" : "☆ Save"}
      <span className="sr-only">{` ${name}`}</span>
    </button>
  );
}
```

`web/app/station/StationView.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ClosureNote } from "@/components/ClosureNote";
import { DayPlan } from "@/components/DayPlan";
import { HourlyChart } from "@/components/HourlyChart";
import { NowPanel } from "@/components/NowPanel";
import { SaveToggle } from "@/components/SaveToggle";
import { SensitiveSwitch } from "@/components/SensitiveSwitch";
import { StaleBanner } from "@/components/StaleBanner";
import { WhyList } from "@/components/WhyList";
import { useData } from "@/lib/data";
import { dateMYT, hourOfIso, timeMYT, weekdayDate } from "@/lib/format";
import { loadSensitive, saveSensitive } from "@/lib/saved";
import type { Hour, StationDetail } from "@/lib/types";

// The id comes from the URL, so only DOE-style ids are ever turned into a fetch path.
export const STATION_ID = /^[A-Z0-9]{3,12}$/;
const CARD = "rounded-2xl border border-[var(--line)] bg-[var(--card)] p-4";

function officialPeak(hours: Hour[]): Hour | null {
  return hours.reduce<Hour | null>(
    (best, h) => (h.official_api !== null && (best === null || h.official_api > (best.official_api ?? -1)) ? h : best),
    null,
  );
}

function outlook(peak: Hour | null): string {
  if (!peak || peak.official_api === null) return "No official API forecast is available for this station.";
  const range = peak.official_low !== null && peak.official_high !== null && peak.official_high > peak.official_low
    ? ` (likely ${peak.official_low}–${peak.official_high})` : "";
  return `Highest 24-hour average expected in the next 48 hours: about ${peak.official_api} around `
    + `${weekdayDate(dateMYT(peak.t))} ${hourOfIso(peak.t)}${range}.`;
}

export function StationView() {
  const raw = useSearchParams().get("id") ?? "";
  const id = STATION_ID.test(raw) ? raw : null;
  const { data, error } = useData<StationDetail>(id ? `/data/stations/${id}.json` : null);
  const [sensitive, setSensitive] = useState(false);
  const [showHours, setShowHours] = useState(false);
  useEffect(() => setSensitive(loadSensitive()), []);
  useEffect(() => {
    if (showHours) document.getElementById("hourly")?.scrollIntoView?.({ behavior: "smooth" });
  }, [showHours]);

  if (!id || (!data && error === "HTTP 404")) {
    return (
      <section className="py-10 text-center">
        <h1 className="text-2xl font-semibold">Station not found</h1>
        <p className="mt-2"><Link href="/stations/" className="text-[var(--accent)] underline">Choose from the list of stations</Link></p>
      </section>
    );
  }
  if (!data) {
    return error ? (
      <p role="alert" className="py-6">We couldn&apos;t load this station. Check your connection; the page tries again every few minutes.</p>
    ) : (
      <p>Loading…</p>
    );
  }
  return (
    <article className="grid gap-4">
      <StaleBanner generatedAt={data.generated_at} />
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">{data.name}</h1>
          <p className="text-[var(--ink-2)]">{`${data.state} · Updated ${timeMYT(data.generated_at)}`}</p>
        </div>
        <SaveToggle id={data.id} name={data.name} />
      </header>
      <div className={CARD}>
        <NowPanel now={data.now} sensitive={sensitive} />
        <div className="mt-4">
          <SensitiveSwitch checked={sensitive} onChange={(value) => { saveSensitive(value); setSensitive(value); }} />
        </div>
      </div>
      <div className={CARD}>
        <DayPlan days={data.days} onShowHours={() => {
          setShowHours(true);
          document.getElementById("hourly")?.scrollIntoView?.({ behavior: "smooth" });
        }} />
      </div>
      <div className={CARD}><WhyList why={data.why} estimated={data.estimated} /></div>
      <div className={CARD}>
        <h2 className="text-lg font-semibold">Official API outlook</h2>
        <p className="mt-1">{outlook(officialPeak(data.hours))}</p>
        <div className="mt-3"><ClosureNote closure={data.closure} /></div>
      </div>
      {showHours && (
        <section id="hourly" className={CARD} aria-labelledby="hourly-heading">
          <h2 id="hourly-heading" className="text-lg font-semibold">Hour by hour, next 48 hours</h2>
          <HourlyChart hours={data.hours} />
        </section>
      )}
    </article>
  );
}
```

`web/app/station/page.tsx`:

```tsx
import { Suspense } from "react";

import { StationView } from "./StationView";

// useSearchParams needs a Suspense boundary in a static export.
export default function StationPage() {
  return (
    <Suspense fallback={<p>Loading…</p>}>
      <StationView />
    </Suspense>
  );
}
```

- [ ] **Step 4: Run the tests, the typecheck and a build**

Run: `npm --prefix web test 2>&1 | tail -4 && npm --prefix web run typecheck 2>&1 | tail -3 && npm --prefix web run build 2>&1 | tail -12`
Expected:
- All tests pass (23 + 19 = 42).
- The typecheck prints nothing.
- The build lists `/station` as a static route (○) with no "useSearchParams() should be wrapped in a suspense boundary" error.

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add web
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(web): station page with plan the day, reasons, official outlook and hour-by-hour chart

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Pick stations (search, grouped by state, save)

**Files:**
- Create: `web/lib/stations.ts`, `web/lib/stations.test.ts`, `web/app/stations/page.tsx`, `web/app/stations/page.test.tsx`

**Interfaces:**
- Consumes: `useData`, `Latest`, `StationSummary`, `BandPill`, `SaveToggle`, `loadSaved`, fixtures.
- Produces:
  - `filterStations(stations, query) -> StationSummary[]`: every word of the query must appear in the name, state or id. Matching ignores case and accents.
  - `groupByState(stations) -> [state, stations][]`: states and the names within them in alphabetical order.

- [ ] **Step 1: Write the failing tests**

`web/lib/stations.test.ts`:

```ts
import { expect, test } from "vitest";

import { makeLatest } from "@/test/fixtures";

import { filterStations, groupByState } from "./stations";

test("search matches name, state or id, ignoring case and word order", () => {
  const all = makeLatest().stations;
  expect(filterStations(all, "selangor").map((s) => s.id)).toEqual(["ZZ01A", "ZZ03C"]);
  expect(filterStations(all, "contoh KAMPUNG").map((s) => s.id)).toEqual(["ZZ03C"]);
  expect(filterStations(all, "zz02b").map((s) => s.id)).toEqual(["ZZ02B"]);
  expect(filterStations(all, "   ")).toHaveLength(3);
});

test("stations are grouped by state, both in alphabetical order", () => {
  expect(groupByState(makeLatest().stations).map(([state, list]) => [state, list.map((s) => s.name)])).toEqual([
    ["Johor", ["Sampleton"]],
    ["Selangor", ["Kampung Contoh", "Testville"]],
  ]);
});
```

`web/app/stations/page.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { loadSaved } from "@/lib/saved";
import { makeLatest } from "@/test/fixtures";

import StationsPage from "./page";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(makeLatest()), { status: 200 })));
});

test("lists every station by state and narrows the list as you type", async () => {
  render(<StationsPage />);
  expect(await screen.findAllByRole("heading", { level: 2 })).toHaveLength(2);
  await userEvent.type(screen.getByRole("searchbox"), "sample");
  expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual(["Johor"]);
  await userEvent.clear(screen.getByRole("searchbox"));
  await userEvent.type(screen.getByRole("searchbox"), "nowhere");
  expect(screen.getByText(/No station matches/)).toBeInTheDocument();
});

test("saving from the list remembers the station", async () => {
  render(<StationsPage />);
  await userEvent.click(await screen.findByRole("button", { name: /Save Testville/ }));
  expect(loadSaved()).toEqual(["ZZ01A"]);
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npm --prefix web test 2>&1 | tail -6`
Expected: FAIL. `./stations` and `./page` (under `app/stations`) can't be resolved.

- [ ] **Step 3: Write the implementation**

`web/lib/stations.ts`:

```ts
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
```

`web/app/stations/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useState } from "react";

import { BandPill } from "@/components/BandPill";
import { SaveToggle } from "@/components/SaveToggle";
import { useData } from "@/lib/data";
import { filterStations, groupByState } from "@/lib/stations";
import type { Latest } from "@/lib/types";

export default function StationsPage() {
  const { data, error } = useData<Latest>("/data/latest.json");
  const [query, setQuery] = useState("");
  const groups = data ? groupByState(filterStations(data.stations, query)) : [];
  return (
    <section>
      <h1 className="text-2xl font-semibold">Choose your stations</h1>
      <p className="mt-1 text-[var(--ink-2)]">
        Save the stations closest to home, school, tuition or sports. Saved stations show on the home page, on this
        device only.
      </p>
      <p className="mt-1"><Link href="/map/" className="text-[var(--accent)] underline">Find stations on the map</Link></p>
      <label className="mt-4 block">
        <span className="text-sm font-medium">Search</span>
        <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Town, state or station id"
               className="mt-1 w-full rounded-lg border border-[var(--line)] bg-[var(--card)] px-3 py-2" />
      </label>
      {!data ? (
        error ? <p role="alert" className="mt-4">We couldn&apos;t load the station list. Check your connection; the page tries again every few minutes.</p>
          : <p className="mt-4">Loading…</p>
      ) : groups.length === 0 ? (
        <p className="mt-4">{`No station matches “${query.trim()}”.`}</p>
      ) : (
        groups.map(([state, list]) => {
          const headingId = `state-${state.replace(/\W+/g, "-")}`;
          return (
            <section key={state} aria-labelledby={headingId} className="mt-6">
              <h2 id={headingId} className="text-lg font-semibold">{state}</h2>
              <ul className="mt-1">
                {list.map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-3 border-b border-[var(--line)] py-2.5">
                    <Link href={`/station/?id=${s.id}`} className="font-medium hover:underline">{s.name}</Link>
                    <span className="flex shrink-0 items-center gap-2">
                      <span className="sr-only">{s.now.real_feel_band ? "Real Feel now:" : "Official API now:"}</span>
                      <BandPill band={s.now.real_feel_band ?? s.now.official_band} />
                      <SaveToggle id={s.id} name={s.name} />
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          );
        })
      )}
    </section>
  );
}
```

- [ ] **Step 4: Run the tests and the typecheck**

Run: `npm --prefix web test 2>&1 | tail -4 && npm --prefix web run typecheck 2>&1 | tail -3`
Expected: all tests pass (42 + 4 = 46), and the typecheck prints nothing.

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add web
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(web): pick stations by search and state, save from the list

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Map of stations, fires and wind with a 48-hour time slider

The map needs every station's 48 hourly bands and winds. `latest.json` has only 24 bands and no wind, and fetching 68 station files would break the "about 3 requests per page" rule. So the forecast job also writes a small `map.json`, used only by this page.

**Files:**
- Modify (pipeline): `pipeline/myhaze/publish.py` (`map_payload` + one docstring line), `pipeline/myhaze/jobs/forecast.py` (write `map.json`), `pipeline/tests/test_publish.py`
- Create (web): `web/lib/geojson.ts`, `web/lib/geojson.test.ts`, `web/components/FireMap.tsx`, `web/app/map/page.tsx`, `web/app/map/page.test.tsx`
- Modify (web): `web/lib/types.ts` (+ `MapStation`, `MapData`), `web/test/fixtures.ts` (+ `makeMap`)

**Interfaces:**
- Produces (pipeline):
  - `map_payload(payloads: list[dict], stations: dict[str, Station], generated_at: datetime) -> dict` with shape `{"generated_at", "times": [t x 48], "stations": [{"id", "name", "state", "lat", "lon", "bands": [band x 48], "wind_from": [int|null x 48], "wind_kmh": [int|null x 48]}]}`.
  - The forecast job writes it as `map.json`.
- Produces (web):
  - `MapData`, `MapStation`, `makeMap()`.
  - `stationsAt(map, hour)`: a GeoJSON FeatureCollection whose point properties are `{id, name, band, wind_to?, wind_kmh?}`. `wind_to = (wind_from + 180) % 360`, so the arrows point downwind.
  - `firesCollection(fires | undefined)`: GeoJSON points with property `{frp}`.
  - `FireMap({ map, fires, hour, onPick })`: MapLibre with the OpenFreeMap Positron style.
  - The map page.

- [ ] **Step 1: Write the failing pipeline test**

Append to `pipeline/tests/test_publish.py`:

```python
def test_map_payload_carries_each_stations_48_hourly_bands_and_winds():
    from myhaze.publish import map_payload

    good = sample_station()
    good["hours"][3]["wind_from"], good["hours"][3]["wind_kmh"] = 224.6, 7.4
    got = map_payload([good], {"CA21B": KLANG}, NOW)
    assert got["times"] == [h["t"] for h in good["hours"]]
    entry = got["stations"][0]
    assert (entry["id"], entry["state"], entry["lat"], entry["lon"]) == ("CA21B", "Selangor", 3.04, 101.45)
    assert entry["bands"] == [h["band"] for h in good["hours"]]
    assert (entry["wind_from"][3], entry["wind_kmh"][3], entry["wind_from"][0]) == (225, 7, None)
```

Run: `uv --directory pipeline run pytest -q tests/test_publish.py 2>&1 | tail -3`
Expected: FAIL with `ImportError: cannot import name 'map_payload'`.

- [ ] **Step 2: Implement it**

In `pipeline/myhaze/publish.py`, add this line to the module docstring after the `accuracy.json` line:

```
map.json            {"generated_at", "times": [t x 48], "stations": [{"id", "name", "state", "lat", "lon",
                     "bands": [band x 48], "wind_from": [deg|null x 48], "wind_kmh": [km/h|null x 48]}]}
```

and add after `latest_entry`:

```python
def map_payload(payloads: list[dict], stations: dict[str, Station], generated_at: datetime) -> dict:
    """map.json: every station's 48 hourly bands and winds, for the map's time slider."""
    def whole(value):
        return None if value is None else int(round(value))

    return {"generated_at": iso(generated_at),
            "times": [h["t"] for h in payloads[0]["hours"]] if payloads else [],
            "stations": [{"id": p["id"], "name": p["name"], "state": p["state"],
                          "lat": stations[p["id"]].lat, "lon": stations[p["id"]].lon,
                          "bands": [h["band"] for h in p["hours"]],
                          "wind_from": [whole(h["wind_from"]) for h in p["hours"]],
                          "wind_kmh": [whole(h["wind_kmh"]) for h in p["hours"]]} for p in payloads]}
```

In `pipeline/myhaze/jobs/forecast.py`, import `map_payload` from `..publish` and add it to `extras`:

```python
        extras = {"fires.json": fires_payload(latest_cells, generated_at),
                  "accuracy.json": accuracy_payload(model, version, store.verification_summary()),
                  "map.json": map_payload(payloads, {s.station_id: s for s in stations}, generated_at)}
```

Run: `uv --directory pipeline run pytest -q 2>&1 | tail -2 && uv --directory pipeline run python -m myhaze.jobs.forecast && ls -l site-data/map.json`
Expected:
- All pipeline tests pass.
- The job prints `forecast: 68 stations written`.
- `site-data/map.json` exists and is under 120 KB.

- [ ] **Step 3: Write the failing web tests**

Add to `web/lib/types.ts`:

```ts
export interface MapStation {
  id: string;
  name: string;
  state: string;
  lat: number;
  lon: number;
  bands: Band[];
  wind_from: (number | null)[];
  wind_kmh: (number | null)[];
}

export interface MapData {
  generated_at: string;
  times: string[];
  stations: MapStation[];
}
```

Add to `web/test/fixtures.ts` (and add `MapData` to its type import):

```ts
export function makeMap(): MapData {
  const hours = makeHours();
  return {
    generated_at: GENERATED,
    times: hours.map((h) => h.t),
    stations: [{
      id: "ZZ01A", name: "Testville", state: "Selangor", lat: 3.0, lon: 101.5, bands: hours.map((h) => h.band),
      wind_from: hours.map((_, h) => (h === 5 ? null : 225)), wind_kmh: hours.map(() => 8),
    }],
  };
}
```

`web/lib/geojson.test.ts`:

```ts
import { expect, test } from "vitest";

import { GENERATED, makeMap } from "@/test/fixtures";

import { firesCollection, stationsAt } from "./geojson";

test("station points carry the chosen hour's band and a downwind bearing", () => {
  const first = stationsAt(makeMap(), 0).features[0];
  expect(first.geometry.coordinates).toEqual([101.5, 3.0]);
  expect(first.properties).toEqual({ id: "ZZ01A", name: "Testville", band: "unhealthy", wind_to: 45, wind_kmh: 8 });
  expect(stationsAt(makeMap(), 5).features[0].properties.wind_to).toBeUndefined();
});

test("fire cells become points at longitude, latitude", () => {
  expect(firesCollection({ generated_at: GENERATED, cells: [[-1.5, 110.25, 812.4]] }).features[0]).toEqual({
    type: "Feature", geometry: { type: "Point", coordinates: [110.25, -1.5] }, properties: { frp: 812.4 },
  });
  expect(firesCollection(undefined).features).toEqual([]);
});
```

`web/app/map/page.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { GENERATED, makeMap } from "@/test/fixtures";

import MapPage from "./page";

// MapLibre needs WebGL, which jsdom lacks; the map itself is checked in the browser (Task 8).
vi.mock("next/dynamic", () => ({
  default: () => function MapStub({ hour }: { hour: number }) {
    return <div data-testid="map">{`hour ${hour}`}</div>;
  },
}));

test("the time slider steps through the 48 hours in Malaysia time, with a band legend", async () => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(
    JSON.stringify(String(url).includes("map.json") ? makeMap() : { generated_at: GENERATED, cells: [] }), { status: 200 })));
  render(<MapPage />);
  const slider = await screen.findByRole("slider", { name: "Time" });
  expect(screen.getByText("Thu 15 Oct 10am")).toBeInTheDocument();
  fireEvent.change(slider, { target: { value: "14" } });
  expect(screen.getByTestId("map")).toHaveTextContent("hour 14");
  expect(screen.getByText("Fri 16 Oct 12am")).toBeInTheDocument();
  for (const word of ["Good", "Moderate", "Unhealthy", "Very unhealthy", "Hazardous"]) {
    expect(screen.getByText(word)).toBeInTheDocument();
  }
});
```

Run: `npm --prefix web test 2>&1 | tail -6`
Expected: FAIL. `./geojson` and `./page` (under `app/map`) can't be resolved.

- [ ] **Step 4: Write the web implementation**

`web/lib/geojson.ts`:

```ts
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
```

`web/components/FireMap.tsx`:

```tsx
"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import maplibregl, { type ExpressionSpecification, type GeoJSONSource } from "maplibre-gl";
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
```

`web/app/map/page.tsx`:

```tsx
"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useState } from "react";

import { BandPill } from "@/components/BandPill";
import { SaveToggle } from "@/components/SaveToggle";
import { BANDS } from "@/lib/bands";
import { useData } from "@/lib/data";
import { dateMYT, hourOfIso, weekdayDate } from "@/lib/format";
import type { Fires, MapData } from "@/lib/types";

// MapLibre is large and needs the browser: it loads only on this page, only on the client.
const FireMap = dynamic(() => import("@/components/FireMap").then((m) => m.FireMap), {
  ssr: false,
  loading: () => <div className="h-[62vh] min-h-[360px] rounded-2xl border border-[var(--line)] p-4">Loading map…</div>,
});

export default function MapPage() {
  const { data, error } = useData<MapData>("/data/map.json");
  const { data: fires } = useData<Fires>("/data/fires.json");
  const [hour, setHour] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  if (!data) {
    return error ? <p role="alert" className="py-6">We couldn&apos;t load the map data. Check your connection; the page tries again every few minutes.</p>
      : <p>Loading…</p>;
  }
  const at = Math.min(hour, data.times.length - 1);
  const time = data.times[at];
  const station = data.stations.find((s) => s.id === picked);
  return (
    <section className="grid gap-3">
      <h1 className="text-2xl font-semibold">Map</h1>
      <p className="text-[var(--ink-2)]">
        Station dots show the forecast Real Feel. Small dark-red dots are fires seen by satellite on the latest full
        day. Arrows show where the wind is blowing.
      </p>
      <FireMap map={data} fires={fires} hour={at} onPick={setPicked} />
      <div>
        <label htmlFor="map-hour" className="font-medium">Time</label>{" "}
        <output htmlFor="map-hour">{`${weekdayDate(dateMYT(time))} ${hourOfIso(time)}`}</output>
        <input id="map-hour" type="range" min={0} max={data.times.length - 1} step={1} value={at}
               onChange={(e) => setHour(Number(e.target.value))} className="mt-1 w-full accent-[var(--accent)]" />
        <div className="flex justify-between text-xs text-[var(--ink-2)]"><span>Now</span><span>+24h</span><span>+48h</span></div>
      </div>
      <div className="flex flex-wrap gap-2" aria-label="Legend">{BANDS.map((b) => <BandPill key={b} band={b} />)}</div>
      {station && (
        <div aria-live="polite" className="rounded-2xl border border-[var(--line)] bg-[var(--card)] p-4">
          <p className="font-semibold">{`${station.name}, ${station.state}`}</p>
          <p className="mt-1 flex items-center gap-2">
            {`Forecast Real Feel at ${hourOfIso(time)}:`} <BandPill band={station.bands[at]} />
          </p>
          <p className="mt-2 flex items-center gap-4">
            <Link href={`/station/?id=${station.id}`} className="text-[var(--accent)] underline">Plan the day</Link>
            <SaveToggle id={station.id} name={station.name} />
          </p>
        </div>
      )}
      <p className="text-sm"><Link href="/stations/" className="underline">Prefer a list? Choose stations from the list</Link></p>
    </section>
  );
}
```

- [ ] **Step 5: Run the tests, the typecheck and a build**

Run: `npm --prefix web test 2>&1 | tail -4 && npm --prefix web run typecheck 2>&1 | tail -3 && npm --prefix web run build 2>&1 | tail -12`
Expected:
- All tests pass (46 + 3 = 49).
- The typecheck prints nothing.
- The build lists `/map` as a static route.

If the typecheck rejects a MapLibre paint or layout literal, fix the types without loosening the runtime behaviour: cast that one expression to `ExpressionSpecification` the way `colourByBand` is cast.

- [ ] **Step 6: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add pipeline web
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat: map of stations, fires and wind with a 48-hour time slider (map.json from the forecast job)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: "How accurate is this?" and About pages

**Files:**
- Create: `web/app/accuracy/page.tsx`, `web/app/accuracy/page.test.tsx`, `web/app/about/page.tsx`, `web/app/about/page.test.tsx`

**Interfaces:**
- Consumes: `useData`, `Accuracy`, `LeadReport`, `MethodScores`, `percent`, `CLOSURE_CAPTION`, `makeAccuracy`.
- Track-record horizons are the keys `"1-24h"` and `"25-48h"` written by Plan 2's verify job.

- [ ] **Step 1: Write the failing tests**

`web/app/accuracy/page.test.tsx`:

```tsx
import { render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { makeAccuracy } from "@/test/fixtures";

import AccuracyPage from "./page";

function serve(body: unknown) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
}

test("backtest tables compare every method, mark the one in use and say plainly that the target is not met", async () => {
  serve(makeAccuracy());
  render(<AccuracyPage />);
  expect(await screen.findByRole("heading", { name: "Tomorrow" })).toBeInTheDocument();
  const tomorrow = screen.getAllByRole("table")[0];
  expect(within(tomorrow).getByText("71%")).toBeInTheDocument();
  expect(within(tomorrow).getByText("58%")).toBeInTheDocument();
  expect(within(tomorrow).getByText(/used on this site/).closest("tr")).toHaveTextContent("MYHaze model");
  expect(screen.getByText(/Target not met yet/)).toBeInTheDocument();
  expect(screen.getByText(/live track record starts/)).toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(/NaN|null|undefined/);
});

test("the live track record shows the checked hours", async () => {
  serve({ ...makeAccuracy(), track_record: {
    "1-24h": { days: 3, hours: 4800, band_accuracy: 0.74, unhealthy_hours: 900, pod_unhealthy: 0.8 } } });
  render(<AccuracyPage />);
  const row = (await screen.findByText("Next 24 hours")).closest("tr")!;
  expect(row).toHaveTextContent("74%");
  expect(row).toHaveTextContent("4800 hours");
});
```

`web/app/about/page.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { CLOSURE_CAPTION } from "@/components/ClosureNote";

import AboutPage from "./page";

test("explains both numbers and carries every credit and disclaimer", () => {
  render(<AboutPage />);
  expect(screen.getByText(CLOSURE_CAPTION)).toBeInTheDocument();
  const text = document.body.textContent ?? "";
  for (const phrase of ["24-hour average", "this hour's air", "not medical advice", "never asks for your location",
    "aqicn.org", "NASA FIRMS", "Open-Meteo", "Copernicus", "OpenStreetMap", "AGPL-3.0"]) {
    expect(text).toContain(phrase);
  }
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `npm --prefix web test 2>&1 | tail -6`
Expected: FAIL. `./page` (under `app/accuracy` and `app/about`) can't be resolved.

- [ ] **Step 3: Write the implementation**

`web/app/accuracy/page.tsx`:

```tsx
"use client";

import { useData } from "@/lib/data";
import { percent } from "@/lib/format";
import type { Accuracy, LeadReport, MethodScores } from "@/lib/types";

const LEADS = [
  ["1", "Tomorrow", "Target: the right band on at least 90% of days, and at least 90% of unhealthy-or-worse days caught."],
  ["2", "The day after", "Aim: the right band on about 80% of days."],
] as const;
const METHODS = [
  ["model", "MYHaze model"],
  ["cams", "Regional smoke forecast (CAMS), corrected"],
  ["persistence", "“Tomorrow looks like today”"],
] as const;
const HORIZONS = [["1-24h", "Next 24 hours"], ["25-48h", "24 to 48 hours ahead"]] as const;

function miss(value: number | null): string {
  return value === null ? "–" : `${value.toFixed(1)} µg/m³`;
}

function LeadSection({ label, aim, lead, report }: { label: string; aim: string; lead: string; report: LeadReport }) {
  const scores: Record<string, MethodScores> = { model: report.model, cams: report.cams, persistence: report.persistence };
  const shipped = scores[report.method];
  return (
    <section className="mt-6">
      <h2 className="text-lg font-semibold">{label}</h2>
      <p className="text-sm text-[var(--ink-2)]">
        {`Tested on ${report.model.n} station-days from ${report.test_from} to ${report.test_to}, days the model never learned from.`}
      </p>
      <div className="overflow-x-auto">
        <table className="mt-2 w-full text-left text-sm">
          <thead>
            <tr><th>Method</th><th>Right band</th><th>Unhealthy days caught</th><th>False alarms</th><th>Typical miss</th></tr>
          </thead>
          <tbody>
            {METHODS.map(([key, name]) => (
              <tr key={key} className="border-t border-[var(--line)]">
                <td>{name}{report.method === key && <span className="ml-1 font-semibold">(used on this site)</span>}</td>
                <td>{percent(scores[key].band_accuracy)}</td>
                <td>{percent(scores[key].pod_unhealthy)}</td>
                <td>{percent(scores[key].far_unhealthy)}</td>
                <td>{miss(scores[key].mae_ugm3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2">{aim}</p>
      {lead === "1" && (
        <p className="mt-1 font-medium">
          {report.meets_target ? "Target met." : `Target not met yet: the forecast in use gets the band right ${percent(shipped?.band_accuracy)} of the time and catches ${percent(shipped?.pod_unhealthy)} of unhealthy days.`}
        </p>
      )}
    </section>
  );
}

export default function AccuracyPage() {
  const { data, error } = useData<Accuracy>("/data/accuracy.json");
  if (!data) {
    return error ? <p role="alert" className="py-6">We couldn&apos;t load the accuracy figures. The page tries again every few minutes.</p>
      : <p>Loading…</p>;
  }
  const record = HORIZONS.filter(([key]) => data.track_record[key]);
  const backtest = data.backtest;
  return (
    <article>
      <h1 className="text-2xl font-semibold">How accurate is this?</h1>
      <p className="mt-2">
        Every forecast here is tested in two ways: on past days the model never saw (the backtest), and against what
        really happened after we published it (the live track record). Both are shown as they are, good or bad.
      </p>
      {backtest ? (
        LEADS.map(([lead, label, aim]) => backtest[lead]
          ? <LeadSection key={lead} label={label} aim={aim} lead={lead} report={backtest[lead]} /> : null)
      ) : (
        <p className="mt-6">No model has been trained yet.</p>
      )}
      <section className="mt-8">
        <h2 className="text-lg font-semibold">Live track record (last 30 days)</h2>
        {record.length === 0 ? (
          <p className="mt-1">The live track record starts after the first full day of published forecasts has been checked against what happened.</p>
        ) : (
          <table className="mt-2 w-full text-left text-sm">
            <thead><tr><th>How far ahead</th><th>Right band</th><th>Unhealthy hours caught</th></tr></thead>
            <tbody>
              {record.map(([key, label]) => {
                const r = data.track_record[key];
                return (
                  <tr key={key} className="border-t border-[var(--line)]">
                    <td>{label}</td>
                    <td>{`${percent(r.band_accuracy)} of ${r.hours} hours over ${r.days} days`}</td>
                    <td>{r.unhealthy_hours ? `${percent(r.pod_unhealthy)} of ${r.unhealthy_hours} hours` : "No unhealthy hours yet"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
      {data.version && <p className="mt-6 text-sm text-[var(--ink-2)]">{`Model version ${data.version}.`}</p>}
    </article>
  );
}
```

`web/app/about/page.tsx`:

```tsx
import Link from "next/link";

import { CLOSURE_CAPTION } from "@/components/ClosureNote";

const H2 = "mt-6 text-lg font-semibold";

export default function AboutPage() {
  return (
    <article className="space-y-2">
      <h1 className="text-2xl font-semibold">About MYHaze</h1>

      <h2 className={H2}>Two numbers, two questions</h2>
      <p>
        <strong>Real Feel</strong> is this hour&apos;s air: the latest hourly PM2.5 reading at the station, put on
        Malaysia&apos;s API scale so it reads like the numbers you know. It changes hour by hour, the way the air outside does.
      </p>
      <p>
        The <strong>official DOE API</strong> is the Department of Environment&apos;s figure, a 24-hour average. It moves
        slowly, so it can still look fine after the air has turned bad, and stay high after the air has cleared.
        School-closure rules use this number.
      </p>

      <h2 className={H2}>Why aqicn.org and IQAir show different numbers</h2>
      <p>
        They use the US AQI scale and shorter averaging times. The same air gets a different number on a different scale.
        MYHaze shows both of its numbers on Malaysia&apos;s API scale so they can be compared with DOE&apos;s.
      </p>

      <h2 className={H2}>How the forecast works</h2>
      <p>
        Every hour MYHaze combines the latest readings with fires seen by NASA satellites in Sumatra, Kalimantan and
        Malaysia, the forecast wind that carries their smoke, forecast rain that washes it out, how well the air mixes
        through the day, and the Copernicus regional smoke forecast. The model learned from Malaysian air-quality data
        from July 2026 and is retrained every week. It is tested against simple alternatives on days it never saw:{" "}
        <Link href="/accuracy/" className="text-[var(--accent)] underline">see how accurate it is</Link>.
      </p>

      <h2 className={H2}>School closures</h2>
      <p>{CLOSURE_CAPTION}</p>

      <h2 className={H2}>Advice</h2>
      <p>
        The short advice under each reading is general guidance adapted from public air-quality advisories. It is not
        medical advice. If your child has asthma or other breathing problems, the &quot;My child is sensitive&quot; switch on a
        station page shows the advice one band earlier.
      </p>

      <h2 className={H2}>Privacy</h2>
      <p>
        MYHaze never asks for your location. There are no accounts, cookies, ads or tracking. Your saved stations and
        settings stay in this browser on this device.
      </p>

      <h2 className={H2}>Data and credits</h2>
      <ul className="list-disc space-y-1 pl-5">
        <li>Department of Environment Malaysia (DOE): official API readings.</li>
        <li>World Air Quality Index Project (aqicn.org): hourly station readings.</li>
        <li>NASA FIRMS: satellite fire detections (VIIRS).</li>
        <li>Open-Meteo (CC BY 4.0): weather forecasts and Copernicus Atmosphere Monitoring Service (CAMS) smoke forecasts. Contains modified Copernicus Atmosphere Monitoring Service information.</li>
        <li>Map: OpenFreeMap, © OpenStreetMap contributors.</li>
      </ul>

      <h2 className={H2}>Source code and licence</h2>
      <p>
        MYHaze is free software under the GNU AGPL-3.0:{" "}
        <a href="https://github.com/kiizenitc/myhaze" className="text-[var(--accent)] underline">read the source on GitHub</a>.
        Anyone who runs a modified copy publicly must publish their changes too.
      </p>
    </article>
  );
}
```

- [ ] **Step 4: Run the tests, the typecheck and a build**

Run: `npm --prefix web test 2>&1 | tail -4 && npm --prefix web run typecheck 2>&1 | tail -3 && npm --prefix web run build 2>&1 | tail -14`
Expected:
- All tests pass (49 + 3 = 52).
- The typecheck prints nothing.
- The build lists `/`, `/station`, `/stations`, `/map`, `/accuracy` and `/about` as static routes.

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add web
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(web): accuracy page (backtest vs baselines, live track record) and About page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Deploy to Cloudflare every hour, then check it in a real browser

**Files:**
- Create: `web/wrangler.jsonc`, `web/public/_headers`, `web/scripts/copy-data.mjs`
- Modify: `.github/workflows/forecast.yml`, `.github/workflows/ci.yml`, `pipeline/tests/test_workflows.py`

**Interfaces:**
- Consumes: the built site in `web/out/`, and the forecast job's `--out` option.
- Produces:
  - The hourly forecast workflow builds the site, writes the data into `web/out/data/`, and deploys with `wrangler` when `CLOUDFLARE_API_TOKEN` is set. Without that secret it uploads the data as an artifact, as before.
  - CI runs the web tests, typecheck and build.
  - The site goes live at `https://myhaze.<account-subdomain>.workers.dev`.

- [ ] **Step 1: Write the failing workflow test**

Append to `pipeline/tests/test_workflows.py`:

```python
def test_the_forecast_workflow_builds_the_site_then_deploys_only_with_cloudflare_secrets():
    text = (REPO_ROOT / ".github" / "workflows" / "forecast.yml").read_text(encoding="utf-8")
    assert text.index("npm --prefix web run build") < text.index("myhaze.jobs.forecast")
    assert '--out "$GITHUB_WORKSPACE/web/out/data"' in text
    assert "if: env.HAS_CLOUDFLARE == 'true'" in text and "npx wrangler deploy" in text


def test_ci_runs_the_web_tests_typecheck_and_build():
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for command in ("npm --prefix web ci", "npm --prefix web test", "npm --prefix web run typecheck",
                    "npm --prefix web run build"):
        assert command in text
```

Run: `uv --directory pipeline run pytest -q tests/test_workflows.py 2>&1 | tail -3`
Expected: FAIL. Neither workflow mentions the web build yet.

- [ ] **Step 2: Write the deployment files**

`web/wrangler.jsonc` (a Worker that only serves static assets: no script, so no request is billed):

```jsonc
{
  "$schema": "./node_modules/wrangler/config-schema.json",
  "name": "myhaze",
  "compatibility_date": "2026-10-01",
  "assets": {
    "directory": "./out",
    "html_handling": "auto-trailing-slash",
    "not_found_handling": "404-page"
  }
}
```

`web/public/_headers`:

```
/data/*
  Cache-Control: public, max-age=60, must-revalidate

/_next/static/*
  Cache-Control: public, max-age=31536000, immutable

/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: geolocation=(), camera=(), microphone=()
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://tiles.openfreemap.org; connect-src 'self' https://tiles.openfreemap.org; worker-src 'self' blob:; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'
```

(`'unsafe-inline'` for scripts is required by the inline bootstrap scripts of a Next static export. `blob:` workers are required by MapLibre. `geolocation=()` makes the no-GPS promise enforceable by the browser.)

`web/scripts/copy-data.mjs`:

```js
// Dev helper: serve the pipeline's latest output (../site-data, git-ignored) at /data while running `next dev`.
import { cpSync, existsSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";

const source = fileURLToPath(new URL("../../site-data/", import.meta.url));
const target = fileURLToPath(new URL("../public/data/", import.meta.url));
if (!existsSync(source)) {
  console.error("No site-data yet: run `uv --directory pipeline run python -m myhaze.jobs.forecast` first.");
  process.exit(1);
}
rmSync(target, { recursive: true, force: true });
cpSync(source, target, { recursive: true });
console.log(`copied ${source} -> ${target}`);
```

Replace the `jobs:` section of `.github/workflows/forecast.yml` with:

```yaml
jobs:
  forecast:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    env:
      HAS_CLOUDFLARE: ${{ secrets.CLOUDFLARE_API_TOKEN != '' }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
        with:
          enable-cache: true
          cache-dependency-glob: pipeline/uv.lock
      - uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version: 24
          cache: npm
          cache-dependency-path: web/package-lock.json
      - name: Install
        run: |
          uv --directory pipeline sync --frozen
          npm --prefix web ci
      - name: Build site
        run: npm --prefix web run build
      - name: Forecast
        run: uv --directory pipeline run python -m myhaze.jobs.forecast --out "$GITHUB_WORKSPACE/web/out/data"
        env:
          SUPABASE_DB_URL: ${{ secrets.SUPABASE_DB_URL }}
      - name: Deploy
        if: env.HAS_CLOUDFLARE == 'true'
        working-directory: web
        run: npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
      - if: env.HAS_CLOUDFLARE != 'true'
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: site-data
          path: web/out/data
          retention-days: 2
```

Append a `web` job to `.github/workflows/ci.yml`:

```yaml
  web:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0
        with:
          node-version: 24
          cache: npm
          cache-dependency-path: web/package-lock.json
      - run: npm --prefix web ci
      - run: npm --prefix web test
      - run: npm --prefix web run typecheck
      - run: npm --prefix web run build
```

- [ ] **Step 3: Run the tests and measure the first load**

Run:

```bash
cd "/Users/ryanchuah/Claude Code/MYHaze"
uv --directory pipeline run pytest -q 2>&1 | tail -2
npm --prefix web run build 2>&1 | tail -3 && ls web/out/_headers
node -e 'const fs=require("fs"),z=require("zlib");const h=fs.readFileSync("web/out/index.html","utf8");const f=[...new Set([...h.matchAll(/(?:src|href)="(\/_next\/[^"]+\.(?:js|css))"/g)].map(m=>m[1]))];let t=z.gzipSync(h).length;let map=false;for(const p of f){const b=fs.readFileSync("web/out"+p);t+=z.gzipSync(b).length;if(b.includes("maplibre"))map=true}console.log(Math.round(t/1024)+" KB gzip, maplibre on home: "+map)'
```

Expected:
- All pipeline tests pass, including both new workflow tests.
- `web/out/_headers` exists.
- The home page's first load is under 150 KB gzip, with `maplibre on home: false`.

- [ ] **Step 4: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add web .github pipeline/tests/test_workflows.py
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "ci: build and deploy the site to Cloudflare from the hourly forecast workflow; web checks in CI

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Confirm Cloudflare's free-plan terms (spec §9)**

Read Cloudflare's current "Workers static assets: billing and limitations" page and the Workers limits page. Confirm three things:
- Requests for static assets are free and unlimited.
- Deploying with `wrangler deploy` has no monthly build quota.
- The per-file (25 MiB) and per-version file-count limits are far above this site's needs (about 100 files).

Record each in the ledger as `Task 8: verified …` with the page URL. If any of these is no longer true, apply the spec's fallback and record a ruling: deploy the site only on code changes, and publish `data/` separately.

- [ ] **Step 6: Owner action — Cloudflare credentials (stop and ask)**

Ask the owner to do the following in the Cloudflare dashboard, then confirm in chat:
1. Create a free Cloudflare account, or sign in.
2. Create an API token from the "Edit Cloudflare Workers" template.
3. Copy the account ID.
4. Add both to `.env` as `CLOUDFLARE_API_TOKEN=` and `CLOUDFLARE_ACCOUNT_ID=`.

Never ask for them in chat. Then copy both into GitHub secrets without printing them:

```bash
cd "/Users/ryanchuah/Claude Code/MYHaze"
for k in CLOUDFLARE_API_TOKEN CLOUDFLARE_ACCOUNT_ID; do grep "^$k=" .env | cut -d= -f2- | tr -d '\n"' | gh secret set "$k" -R kiizenitc/myhaze; done
gh secret list -R kiizenitc/myhaze | cut -f1
```

Expected: the list shows `AQICN_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `FIRMS_MAP_KEY` and `SUPABASE_DB_URL`.

- [ ] **Step 7: First deploy from this machine**

```bash
cd "/Users/ryanchuah/Claude Code/MYHaze"
npm --prefix web run build >/dev/null && uv --directory pipeline run python -m myhaze.jobs.forecast --out "$PWD/web/out/data"
( set -a; . ./.env; set +a; cd web && npx wrangler deploy 2>&1 | grep -E "Uploaded|Deployed|https://|error" )
```

Expected: `wrangler` prints the deployed `https://myhaze.<subdomain>.workers.dev` URL. Record that URL in the ledger.

- [ ] **Step 8: Check the live site in the built-in browser**

Open the workers.dev URL in the built-in browser (`mcp__Claude_Browser__preview_start` with `url`) and check each item. Record each result in the ledger.

1. Mobile width (`resize_window` preset `mobile`). On Home, the empty state's "Choose your stations" link goes to the list.
2. Save two stations from different states. Home shows two cards with Real Feel, the official API, the 24-hour strip, the closure note and "Updated …".
3. Open a station page:
   - Tomorrow's tab is selected.
   - The blocks show bands with "worst ~".
   - "See hour-by-hour forecast" opens the chart, the tooltip follows a tap, and the table view works.
   - The sensitive switch changes the advice.
4. Map:
   - Tiles load.
   - Station dots are coloured, and fire dots and wind arrows show.
   - Moving the slider recolours the dots.
   - Tapping a dot shows its panel.
5. The Accuracy and About pages read correctly. The footer credits every source on every page.
6. Dark mode (`resize_window` with `colorScheme: "dark"`): text is readable and band pills keep their words.
7. `read_console_messages` with `onlyErrors: true` shows no errors, in particular no Content-Security-Policy violations. If MapLibre fetches from another OpenFreeMap host, add that host to `img-src`/`connect-src` in `_headers`, rebuild, redeploy and recheck.
8. `read_network_requests` on Home shows only our own `/data/latest.json` and `/_next/…` files: no third-party requests.

Reset the viewport (`resize_window` preset `desktop`) when done.

- [ ] **Step 9: Owner review of the advice text (stop and ask)**

Show the owner, in chat, the exact wording of all of these:
- `ADVICE` (all five bands);
- the sensitive-switch label;
- `CLOSURE_CAPTION` and the closure sentence pattern ("School closure rule for Fri 16 Oct: Possible (62%), mainly through …");
- the About page's "Advice" paragraph.

Apply the owner's edits exactly, update any test that quotes the changed text, and run `npm --prefix web test`. Record `Task 8: owner approved advice text` in the ledger.

- [ ] **Step 10: Commit any fixes from QA and review**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add web
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "fix(web): QA and owner-review adjustments

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

(Skip the commit if nothing changed.)

---

### Task 9: A reliable clock: a Cloudflare cron that starts the GitHub workflows

On 15 Oct GitHub's `schedule` trigger fired zero times in over three hours on the new repo, while manually dispatched runs always started within seconds. GitHub documents scheduled runs as best-effort: they can be delayed or dropped. A Cloudflare Worker Cron Trigger, which is free and fires on time, calls GitHub's `workflow_dispatch` API instead. The GitHub `schedule:` lines stay as a fallback. Every job is idempotent, and each workflow's concurrency group queues any overlap.

**Files:**
- Create: `scheduler/package.json` (via npm), `scheduler/tsconfig.json`, `scheduler/wrangler.jsonc`, `scheduler/src/schedule.ts`, `scheduler/src/schedule.test.ts`, `scheduler/src/index.ts`
- Modify: `.gitignore`, `.github/workflows/ci.yml`, `pipeline/tests/test_workflows.py`

**Interfaces:**
- Produces:
  - `workflowsDue(at: Date) -> string[]`. It is called every 5 minutes (UTC): archive at :05, :20, :35 and :50; forecast at :25; verify at 18:30 UTC; train on Saturday at 19:00 UTC (Sunday 03:00 MYT).
  - `dispatch(workflow, env, fetcher)`: POSTs `{"ref": "main"}` to the workflow's dispatch endpoint and throws `"<workflow>: GitHub answered <status>"` on any error status.
  - A Worker named `myhaze-scheduler` with cron `*/5 * * * *` and no public URL.

- [ ] **Step 1: Install the toolchain**

```bash
mkdir -p "/Users/ryanchuah/Claude Code/MYHaze/scheduler/src" && cd "/Users/ryanchuah/Claude Code/MYHaze/scheduler" && npm init -y >/dev/null
npm install -D typescript@5.9 vitest@5 wrangler@4
npm pkg set name=myhaze-scheduler license=AGPL-3.0-only private=true --json
npm pkg set scripts.test="vitest run" scripts.typecheck="tsc --noEmit" scripts.deploy="wrangler deploy"
npm pkg delete main
printf '\n# scheduler\nscheduler/node_modules/\nscheduler/.wrangler/\n' >> ../.gitignore
```

`scheduler/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["es2022", "webworker"],
    "module": "esnext",
    "moduleResolution": "bundler",
    "strict": true,
    "noEmit": true,
    "skipLibCheck": true,
    "isolatedModules": true
  },
  "include": ["src"]
}
```

`scheduler/wrangler.jsonc`:

```jsonc
{
  "$schema": "./node_modules/wrangler/config-schema.json",
  "name": "myhaze-scheduler",
  "main": "src/index.ts",
  "compatibility_date": "2026-10-01",
  "workers_dev": false,
  "triggers": { "crons": ["*/5 * * * *"] },
  "vars": { "REPO": "kiizenitc/myhaze" },
  "observability": { "enabled": true }
}
```

- [ ] **Step 2: Write the failing tests**

`scheduler/src/schedule.test.ts`:

```ts
import { expect, test } from "vitest";

import { dispatch, workflowsDue } from "./schedule";

const due = (iso: string) => workflowsDue(new Date(iso));

test("archive every 15 minutes, forecast at :25, verify and train at their Malaysia-time slots", () => {
  expect(due("2026-10-15T06:05:00Z")).toEqual(["archive.yml"]);
  expect(due("2026-10-15T06:50:00Z")).toEqual(["archive.yml"]);
  expect(due("2026-10-15T06:25:00Z")).toEqual(["forecast.yml"]);
  expect(due("2026-10-15T06:10:00Z")).toEqual([]);
  expect(due("2026-10-15T18:30:00Z")).toEqual(["verify.yml"]);
  expect(due("2026-10-17T19:00:00Z")).toEqual(["train.yml"]); // Saturday 19:00 UTC = Sunday 03:00 in Malaysia
  expect(due("2026-10-16T19:00:00Z")).toEqual([]);
});

test("dispatch asks GitHub to run the workflow on main, and fails loudly when GitHub refuses", async () => {
  const calls: [string, RequestInit][] = [];
  const ok = async (url: string, init: RequestInit) => {
    calls.push([url, init]);
    return new Response(null, { status: 204 });
  };
  const env = { GITHUB_TOKEN: "test-token", REPO: "kiizenitc/myhaze" };
  await dispatch("archive.yml", env, ok);
  expect(calls[0][0]).toBe("https://api.github.com/repos/kiizenitc/myhaze/actions/workflows/archive.yml/dispatches");
  expect(calls[0][1].method).toBe("POST");
  expect(JSON.parse(String(calls[0][1].body))).toEqual({ ref: "main" });
  await expect(dispatch("archive.yml", env, async () => new Response("no", { status: 401 })))
    .rejects.toThrow("archive.yml: GitHub answered 401");
});
```

Run: `npm --prefix scheduler test 2>&1 | tail -5`
Expected: FAIL. It can't resolve `./schedule`.

- [ ] **Step 3: Write the implementation**

`scheduler/src/schedule.ts`:

```ts
// GitHub's own cron is best-effort and was silent for hours on this new repo; a Worker Cron Trigger is not.
// The Worker fires every 5 minutes (UTC) and asks GitHub to run whichever workflows are due.

export interface Env {
  GITHUB_TOKEN: string;
  REPO: string;
}

export type Fetcher = (url: string, init: RequestInit) => Promise<Response>;

export function workflowsDue(at: Date): string[] {
  const minute = at.getUTCMinutes();
  const hour = at.getUTCHours();
  const due: string[] = [];
  if (minute % 15 === 5) due.push("archive.yml"); // :05 :20 :35 :50
  if (minute === 25) due.push("forecast.yml"); // after the :20 archive
  if (hour === 18 && minute === 30) due.push("verify.yml"); // 02:30 Malaysia time
  if (at.getUTCDay() === 6 && hour === 19 && minute === 0) due.push("train.yml"); // Sunday 03:00 Malaysia time
  return due;
}

export async function dispatch(workflow: string, env: Env, fetcher: Fetcher): Promise<void> {
  const response = await fetcher(`https://api.github.com/repos/${env.REPO}/actions/workflows/${workflow}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "myhaze-scheduler",
    },
    body: JSON.stringify({ ref: "main" }),
  });
  if (!response.ok) throw new Error(`${workflow}: GitHub answered ${response.status}`);
}
```

`scheduler/src/index.ts`:

```ts
import { dispatch, type Env, workflowsDue } from "./schedule";

interface ScheduledController {
  scheduledTime: number;
}

export default {
  async scheduled(controller: ScheduledController, env: Env): Promise<void> {
    // Awaited, so a failed dispatch marks this cron run as failed in Cloudflare's logs.
    await Promise.all(workflowsDue(new Date(controller.scheduledTime)).map((w) => dispatch(w, env, fetch)));
  },
};
```

Add the scheduler checks to the `web` job in `.github/workflows/ci.yml`, after its last step:

```yaml
      - run: npm --prefix scheduler ci
      - run: npm --prefix scheduler test
      - run: npm --prefix scheduler run typecheck
```

Append to `pipeline/tests/test_workflows.py`:

```python
def test_ci_runs_the_scheduler_tests():
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "npm --prefix scheduler test" in text and "npm --prefix scheduler run typecheck" in text
```

- [ ] **Step 4: Run all checks**

Run: `npm --prefix scheduler test 2>&1 | tail -3 && npm --prefix scheduler run typecheck 2>&1 | tail -2 && uv --directory pipeline run pytest -q 2>&1 | tail -2`
Expected: 2 scheduler tests pass, the typecheck prints nothing, and all pipeline tests pass.

- [ ] **Step 5: Commit**

```bash
git -C "/Users/ryanchuah/Claude Code/MYHaze" add .gitignore .github scheduler pipeline/tests/test_workflows.py
git -C "/Users/ryanchuah/Claude Code/MYHaze" status --short | grep -E "node_modules|\.wrangler" && echo "STOP: build output staged" || true
git -C "/Users/ryanchuah/Claude Code/MYHaze" commit -m "feat(scheduler): Cloudflare cron that dispatches the GitHub workflows on time

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Owner action — a GitHub token that can only start workflows (stop and ask)**

Ask the owner to create a **fine-grained personal access token** on GitHub (Settings → Developer settings → Fine-grained tokens):
- Resource owner: `kiizenitc`. Repository access: only `kiizenitc/myhaze`.
- Repository permissions: **Actions: Read and write**. Leave everything else at No access.
- Expiry: the longest they are comfortable with. Note the date: the scheduler stops when the token expires.

The owner adds it to `.env` as `GH_DISPATCH_TOKEN=` and confirms in chat. Never ask for the token itself in chat.

- [ ] **Step 7: Deploy the scheduler, give it the token, and watch it fire**

```bash
cd "/Users/ryanchuah/Claude Code/MYHaze"
( set -a; . ./.env; set +a; cd scheduler && npx wrangler deploy 2>&1 | grep -E "Uploaded|Deployed|schedule|error" )
( set -a; . ./.env; set +a; cd scheduler && grep '^GH_DISPATCH_TOKEN=' ../.env | cut -d= -f2- | tr -d '\n"' | npx wrangler secret put GITHUB_TOKEN 2>&1 | tail -1 )
```

Expected: the deploy lists the schedule `*/5 * * * *`, and `secret put` reports success. The token value is never printed.

Wait for the next :05/:20/:35/:50 slot, plus about a minute. Then run:

```bash
gh run list -R kiizenitc/myhaze -L 6 --json workflowName,event,createdAt --jq '.[] | "\(.workflowName) \(.event) \(.createdAt)"'
```

Expected: an `archive workflow_dispatch` run created within about a minute of the slot. After the next :25, a `forecast workflow_dispatch` run appears and deploys the site. Record both in the ledger. Then stop the Mac backup runner if it is still running: it is no longer needed.

