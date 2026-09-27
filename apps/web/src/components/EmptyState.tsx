// Generic empty state (ui-guidelines §1.4): always offers one next action.
// Presentational only — pages decide when it renders (B8 wires real routes).

import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
  icon = "◌",
}: {
  title: string;
  description?: string;
  action?: ReactNode; // e.g. <Link className="btn-primary">Apply for a service</Link>
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-zinc-300 bg-zinc-50 px-6 py-12 text-center">
      <span aria-hidden="true" className="text-3xl text-zinc-400">
        {icon}
      </span>
      <h3 className="text-base font-semibold text-zinc-800">{title}</h3>
      {description && (
        <p className="max-w-sm text-sm text-zinc-500">{description}</p>
      )}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
