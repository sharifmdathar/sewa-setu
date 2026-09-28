"use client";

// Compact multi-select risk filter, mirroring StatusFilter so the two dropdowns behave the
// same way: a <details> popover whose checkboxes live in the DOM even when closed, so the
// no-JS GET form still submits them, and a summary that tracks the live selection count.
//
// The bands match the dashboard histogram, not a second private definition: high >= 60,
// medium >= 30, low < 30 (rules.yaml flagThreshold / cleanCeiling). The old single-select
// offered only "High (>=60)" and "Low (<60)", which folded the middle band into "low" and so
// disagreed with the chart on the same screen.

import { useRef, useState } from "react";
import type { RiskBand } from "@/components/RiskMeter";

export type { RiskBand };

const LABELS: Record<RiskBand, string> = {
  high: "High (≥60)",
  medium: "Medium (30–59)",
  low: "Low (<30)",
};

export function RiskFilter({
  options,
  selected,
}: {
  options: RiskBand[];
  selected: RiskBand[];
}) {
  const groupRef = useRef<HTMLFieldSetElement>(null);
  const [count, setCount] = useState(selected.length);
  const allChecked = count === options.length;

  const boxes = () =>
    Array.from(
      groupRef.current?.querySelectorAll<HTMLInputElement>('input[name="risk"]') ??
        [],
    );

  function toggleAll() {
    const next = !allChecked;
    for (const b of boxes()) b.checked = next;
    setCount(next ? options.length : 0);
  }

  function sync() {
    setCount(boxes().filter((b) => b.checked).length);
  }

  return (
    <details className="relative">
      <summary className="inline-flex min-h-10 cursor-pointer list-none items-center gap-2 rounded-md border border-zinc-300 bg-white px-3 text-sm font-medium text-zinc-700 hover:border-brand-500 [&::-webkit-details-marker]:hidden">
        Risk: {count} of {options.length}
        <span aria-hidden="true" className="text-zinc-400">
          ▾
        </span>
      </summary>
      <div className="absolute left-0 z-20 mt-1 w-60 rounded-lg border border-zinc-200 bg-white p-3 shadow-lg">
        <button
          type="button"
          onClick={toggleAll}
          className="mb-2 min-h-10 w-full rounded-md border border-zinc-300 px-3 text-xs font-medium text-zinc-700 hover:border-brand-500"
        >
          {allChecked ? "Deselect all" : "Select all"}
        </button>
        <fieldset ref={groupRef} className="space-y-0.5">
          <legend className="sr-only">Filter by risk band</legend>
          {options.map((band) => (
            <label
              key={band}
              className="flex min-h-10 cursor-pointer items-center gap-2 text-sm"
            >
              <input
                type="checkbox"
                name="risk"
                value={band}
                defaultChecked={selected.includes(band)}
                onChange={sync}
                className="h-4 w-4 rounded border-zinc-300 text-brand-600 focus:ring-brand-500"
              />
              {LABELS[band]}
            </label>
          ))}
        </fieldset>
      </div>
    </details>
  );
}
