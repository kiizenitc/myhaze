"use client";

import { useEffect, useState } from "react";

import { loadSaved, toggleSaved } from "@/lib/saved";

export function SaveToggle({ id, name }: { id: string; name: string }) {
  const [saved, setSaved] = useState(false);
  useEffect(() => setSaved(loadSaved().includes(id)), [id]);
  const word = saved ? "Saved" : "Save";
  return (
    <button type="button" aria-pressed={saved} aria-label={`${word} ${name}`}
            onClick={() => setSaved(toggleSaved(id).includes(id))}
            className={`rounded-full border px-3 py-1.5 text-sm font-semibold ${saved
              ? "border-[var(--accent)] text-[var(--accent)]" : "border-[var(--line)]"}`}>
      <span aria-hidden>{saved ? "★" : "☆"}</span> {word}
    </button>
  );
}
