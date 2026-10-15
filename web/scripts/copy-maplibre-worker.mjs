// MapLibre 6 loads its web worker from a file next to its own script. Bundled, that file is missing,
// so ship the installed version's worker as a static file; FireMap points MapLibre at it.
import { copyFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const from = fileURLToPath(new URL("../node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url));
const dir = fileURLToPath(new URL("../public/", import.meta.url));
mkdirSync(dir, { recursive: true });
copyFileSync(from, `${dir}maplibre-gl-worker.mjs`);
