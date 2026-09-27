// Generic error state (ui-guidelines §3): failures show a message + retry,
// never a blank screen and never raw internals on citizen surfaces.
// B7 (RealApiClient) will add typed API error mapping on top of this.

import type { ReactNode } from "react";

export function ErrorState({
  title = "Something went wrong",
  message,
  retry,
}: {
  title?: string;
  message?: string;
  retry?: ReactNode; // e.g. a server-action re-render button
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center gap-3 rounded-lg border border-red-200 bg-red-50 px-6 py-12 text-center"
    >
      <span aria-hidden="true" className="text-3xl text-red-400">
        ⚠
      </span>
      <h3 className="text-base font-semibold text-red-800">{title}</h3>
      {message && <p className="max-w-sm text-sm text-red-700">{message}</p>}
      {retry && <div className="mt-1">{retry}</div>}
    </div>
  );
}

/** Safe one-liner for rendering alongside ErrorState without leaking stacks. */
export function errorToMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  return "Unexpected error. Please try again.";
}
