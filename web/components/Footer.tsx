import Link from "next/link";

export function Footer() {
  return (
    <footer className="mx-auto max-w-[max(1200px,80vw)] px-4 pb-8 text-sm text-[var(--ink-2)]">
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
