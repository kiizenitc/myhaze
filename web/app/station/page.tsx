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
