import Link from "next/link";

import { CLOSURE_CAPTION } from "@/components/ClosureNote";

const H2 = "mt-6 text-lg font-semibold";

export default function AboutPage() {
  return (
    <article className="max-w-3xl space-y-2">
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
