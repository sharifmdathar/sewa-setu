// Renders contract AppStatus (src/lib/api/types.ts) as a colour+text badge.
// Single source of truth for status semantics (docs/track-b/ui-guidelines.md §3).

import type { AppStatus } from "@/lib/api/types";

const STATUS_META: Record<
  AppStatus,
  { label: string; className: string; dot: string }
> = {
  submitted: {
    label: "Submitted",
    className: "bg-blue-50 text-blue-700 ring-blue-200",
    dot: "bg-blue-500",
  },
  documents_uploaded: {
    label: "Documents uploaded",
    className: "bg-blue-50 text-blue-700 ring-blue-200",
    dot: "bg-blue-500",
  },
  scrutiny_pending: {
    label: "Scrutiny pending",
    className: "bg-amber-50 text-amber-700 ring-amber-200",
    dot: "bg-amber-500",
  },
  scrutiny_done: {
    label: "Scrutiny done",
    className: "bg-amber-50 text-amber-700 ring-amber-200",
    dot: "bg-amber-500",
  },
  decided: {
    label: "Decided",
    className: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    dot: "bg-emerald-500",
  },
  info_requested: {
    label: "Info requested",
    className: "bg-rose-50 text-rose-700 ring-rose-200",
    dot: "bg-rose-500",
  },
};

export function statusLabel(status: AppStatus): string {
  return STATUS_META[status].label;
}

export function StatusBadge({ status }: { status: AppStatus }) {
  const meta = STATUS_META[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${meta.className}`}
    >
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
}
