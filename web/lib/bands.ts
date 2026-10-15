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
