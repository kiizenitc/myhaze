"use client";

export function SensitiveSwitch({ checked, onChange }: { checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex items-start gap-3">
      <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)}
             className="mt-1 h-5 w-5 accent-[var(--accent)]" />
      <span>My child is sensitive (asthma or other breathing problems): show advice one band earlier</span>
    </label>
  );
}
