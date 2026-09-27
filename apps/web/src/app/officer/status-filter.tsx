"use client";

// Compact multi-select status filter rendered as a dropdown (<details>
// popover) so the queue toolbar stays on one line. The checkboxes live inside
// the panel and keep the surrounding no-JS GET form working (<details> content
// is always in the DOM, so values submit even when closed). The summary shows a
// live "n of m" count that tracks checkbox changes.

import { useRef, useState } from "react";
import type { AppStatus } from "@/lib/api/types";

export function StatusFilter({
  options,
  selected,
}: {
  options: AppStatus[];
  selected: AppStatus[];
}) {
  const groupRef = useRef<HTMLFieldSetElement>(null);
  const [count, setCount] = useState(selected.length);
  const allChecked = count === options.length;

  const boxes = () =>
    Array.from(
      groupRef.current?.querySelectorAll<HTMLInputElement>(
        'input[name="status"]',
      ) ?? [],
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
      <summary className="inline-flex min-h-10 cursor-pointer list-none items-center gap-2 rounded-md border border-zinc-300 bg-white px-3 text-sm font-medium text-zinc-700 hover:border-zinc-900 [&::-webkit-details-marker]:hidden">
        Status: {count} of {options.length}
        <span aria-hidden="true" className="text-zinc-400">
          ▾
        </span>
      </summary>
      <div className="absolute left-0 z-20 mt-1 w-60 rounded-lg border border-zinc-200 bg-white p-3 shadow-lg">
        <button
          type="button"
          onClick={toggleAll}
          className="mb-2 min-h-10 w-full rounded-md border border-zinc-300 px-3 text-xs font-medium text-zinc-700 hover:border-zinc-900"
        >
          {allChecked ? "Deselect all" : "Select all"}
        </button>
        <fieldset ref={groupRef} className="space-y-0.5">
          <legend className="sr-only">Filter by status</legend>
          {options.map((s) => (
            <label
              key={s}
              className="flex min-h-10 cursor-pointer items-center gap-2 text-sm"
            >
              <input
                type="checkbox"
                name="status"
                value={s}
                defaultChecked={selected.includes(s)}
                onChange={sync}
                className="h-4 w-4 rounded border-zinc-300 text-zinc-900 focus:ring-zinc-900"
              />
              {s}
            </label>
          ))}
        </fieldset>
      </div>
    </details>
  );
}
