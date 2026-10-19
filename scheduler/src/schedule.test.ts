import { expect, test } from "vitest";

import { dispatch, workflowsDue } from "./schedule";

const due = (iso: string) => workflowsDue(new Date(iso));

test("archive every 15 minutes, a forecast 5 minutes after each, verify and train at their Malaysia-time slots", () => {
  expect(due("2026-10-15T06:05:00Z")).toEqual(["archive.yml"]);
  expect(due("2026-10-15T06:50:00Z")).toEqual(["archive.yml"]);
  // aqicn posts each hour some time after :05, so a forecast follows every archive pass and the site trails aqicn
  // by about 20 minutes at most, not 50
  for (const minute of ["10", "25", "40", "55"]) expect(due(`2026-10-15T06:${minute}:00Z`)).toEqual(["forecast.yml"]);
  expect(due("2026-10-15T06:15:00Z")).toEqual([]);
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
