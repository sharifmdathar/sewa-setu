"use client";

// Client form for the dynamic application (J1 step 2). Posts straight to the
// server action (progressive enhancement: works without JS enabled).

import { createApplicationAction } from "../../../actions";
import type { FieldDef } from "@/lib/fields";

// Submission is handled entirely by <form action={serverAction}> (React's
// built-in form-action transition). We deliberately do NOT add a useTransition
// or onClick to the submit button: in React 18.3 a competing transition there
// can race the form action and swallow the submit (no request, no error).
// useFormStatus is not a runtime export of react-dom 18.3.1, so the button
// stays enabled; the action redirects away, so double-submit isn't a concern.

export function ApplyForm({
  serviceId,
  fields,
}: {
  serviceId: string;
  fields: { name: string; def: FieldDef }[];
}) {
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
              className="min-h-12 w-full rounded-md border border-zinc-300 px-3 py-3 text-base focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          ) : (
            <input
              id={`field-${name}`}
              name={name}
              type={def.type === "date" ? "date" : "text"}
              required={def.required}
              className="min-h-12 w-full rounded-md border border-zinc-300 px-3 py-3 text-base focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          )}
        </div>
      ))}
      <button
        type="submit"
        className="min-h-12 w-full rounded-md bg-brand-600 px-5 py-3 text-base font-semibold text-white hover:bg-brand-700"
      >
        Submit application
      </button>
    </form>
  );
}
