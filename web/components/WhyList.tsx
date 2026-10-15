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
