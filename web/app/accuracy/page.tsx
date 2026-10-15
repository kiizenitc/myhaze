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
    <article className="max-w-3xl">
      <h1 className="text-2xl font-semibold">How accurate is this?</h1>
      <p className="mt-2">
        Every forecast here is tested in two ways: on past days the model never saw (the backtest), and against what
        really happened after we published it (the live track record). Both are shown as they are, good or bad.
      </p>
      <p className="mt-2 text-[var(--ink-2)]">
        How sure are these numbers? The backtest covers about a thousand station-days from a single haze season, so
        each percentage could be a few points higher or lower. It scores daily averages; for hour-by-hour accuracy,
        only the live track record below can tell.
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
