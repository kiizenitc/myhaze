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
