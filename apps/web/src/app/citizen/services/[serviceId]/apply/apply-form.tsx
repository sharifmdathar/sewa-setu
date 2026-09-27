"use client";

// Client form for the dynamic application (J1 step 2). Posts straight to the
// server action (progressive enhancement: works without JS enabled).

import { useTransition } from "react";
import { createApplicationAction } from "../../../actions";
import type { FieldDef } from "@/lib/fields";

export function ApplyForm({
  serviceId,
  fields,
}: {
  serviceId: string;
  fields: { name: string; def: FieldDef }[];
}) {
  const [pending, startTransition] = useTransition();

  return (
    <form
      action={createApplicationAction}
      className="space-y-5 rounded-lg border border-zinc-200 bg-white p-6"
    >
      <input type="hidden" name="serviceId" value={serviceId} />
      {fields.map(({ name, def }) => (
        <div key={name} className="space-y-1.5">
          <label htmlFor={`field-${name}`} className="block text-sm font-medium">
            {def.label}
            {def.required && <span className="text-red-600"> *</span>}
          </label>
          {def.type === "number" ? (
            <input
              id={`field-${name}`}
              name={name}
              type="number"
              inputMode="numeric"
              min={0}
              required={def.required}
              className="min-h-12 w-full rounded-md border border-zinc-300 px-3 py-3 text-base focus:border-zinc-900 focus:outline-none focus:ring-1 focus:ring-zinc-900"
            />
          ) : (
            <input
              id={`field-${name}`}
              name={name}
              type={def.type === "date" ? "date" : "text"}
              required={def.required}
              className="min-h-12 w-full rounded-md border border-zinc-300 px-3 py-3 text-base focus:border-zinc-900 focus:outline-none focus:ring-1 focus:ring-zinc-900"
            />
          )}
        </div>
      ))}
      <button
        type="submit"
        disabled={pending}
        onClick={() => startTransition(() => {})}
        className="min-h-12 w-full rounded-md bg-zinc-900 px-5 py-3 text-base font-semibold text-white hover:bg-zinc-700 disabled:opacity-60"
      >
        {pending ? "Submitting…" : "Submit application"}
      </button>
    </form>
  );
}
