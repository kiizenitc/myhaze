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
