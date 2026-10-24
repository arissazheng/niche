"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Measurements, Sizes } from "@/lib/types";

const FIELDS: [keyof Omit<Measurements, "unit">, string, string][] = [
  ["shoulder", "Shoulder to shoulder", "across the back"],
  ["bust", "Bust", "fullest part"],
  ["waist", "Waist", "narrowest part"],
  ["hips", "Hips", "fullest part"],
  ["inseam", "Leg length", "inseam, crotch to ankle"],
  ["arm", "Arm length", "shoulder to wrist"],
];

const SIZE_NAMES: [keyof Sizes, string][] = [["top", "Tops"], ["bottom", "Pants & skirts"], ["bottom_length", "Length"]];
const LENGTH_NAMES: Record<string, string> = { short: "Short (petite)", regular: "Regular", long: "Long (tall)" };

/** Optional body measurements: any, not all. Previews the sizes they point to and can fill empty size picks. */
export function MeasurementsPanel({
  value,
  onChange,
  onUseSizes,
}: {
  value: Measurements;
  onChange: (next: Measurements) => void;
  onUseSizes: (sizes: Partial<Sizes>) => void;
}) {
  const given = FIELDS.some(([key]) => value[key] != null);
  const [open, setOpen] = useState(given);
  const [suggested, setSuggested] = useState<Partial<Sizes> | null>(null);

  useEffect(() => {
    if (!given) return setSuggested(null);
    const timer = setTimeout(() => api.suggestSizes(value).then(setSuggested, () => setSuggested(null)), 300);
    return () => clearTimeout(timer);
  }, [value, given]);

  // What's typed is kept as text, so "36." stays on screen while someone is entering "36.5".
  const [text, setText] = useState<Record<string, string>>(() =>
    Object.fromEntries(FIELDS.map(([key]) => [key, value[key] != null ? String(value[key]) : ""])),
  );
  const set = (key: keyof Omit<Measurements, "unit">, typed: string) => {
    setText((t) => ({ ...t, [key]: typed }));
    const number = parseFloat(typed);
    onChange({ ...value, [key]: typed.trim() && number > 0 ? number : null });
  };
  const picks = SIZE_NAMES.filter(([key]) => suggested?.[key]);

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="label border border-ink px-3 py-2 mt-3">
        + Add my measurements (optional)
      </button>
    );
  }
  return (
    <div className="border border-ink p-4 mt-3 grid gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-display">Your measurements</p>
        <div className="flex gap-1" role="group" aria-label="Units">
          {(["in", "cm"] as const).map((unit) => (
            <button
              type="button"
              key={unit}
              onClick={() => onChange({ ...value, unit })}
              aria-pressed={value.unit === unit}
              className={`label border border-ink px-2 py-1 ${value.unit === unit ? "bg-ink text-paper" : ""}`}
            >
              {unit === "in" ? "Inches" : "cm"}
            </button>
          ))}
        </div>
      </div>
      <p className="text-sm">
        Fill in any you know. We turn them into sizes, and check them against listings that show measurements. They
        only help with fit and are never part of your style profile.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {FIELDS.map(([key, label, hint]) => (
          <label key={key} className="grid gap-1">
            <span className="label">{label}</span>
            <span className="flex items-baseline gap-1">
              <input
                className="input w-20"
                inputMode="decimal"
                value={text[key]}
                onChange={(e) => set(key, e.target.value)}
                aria-describedby={`${key}-hint`}
              />
              <span className="text-sm">{value.unit}</span>
            </span>
            <span id={`${key}-hint`} className="text-xs text-muted">{hint}</span>
          </label>
        ))}
      </div>
      {picks.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 rule-t pt-3" role="status">
          <span className="text-sm">
            Your measurements suggest{" "}
            {picks.map(([key, name], i) => (
              <span key={key}>
                {i > 0 && " · "}
                {name}: <strong>{key === "bottom_length" ? LENGTH_NAMES[suggested![key] as string] : suggested![key]}</strong>
              </span>
            ))}
            . Charts vary by brand, so treat these as a starting point.
          </span>
          <button type="button" onClick={() => suggested && onUseSizes(suggested)} className="label border border-ink px-3 py-1">
            Use these sizes
          </button>
        </div>
      )}
    </div>
  );
}
