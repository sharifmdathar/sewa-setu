// Renders ScrutinyCheck[] (contract type) — every row shows status + severity;
// evidence + explanation expand in place and are NEVER hidden behind navigation
// (SPEC §5/§8.3, ui-guidelines §2/§3). <details> keeps it JS-free.

import type { ScrutinyCheck } from "@/lib/api/types";

const CHECK_STATUS: Record<
  ScrutinyCheck["status"],
  { label: string; badge: string; icon: string }
> = {
  pass: { label: "Pass", badge: "bg-emerald-50 text-emerald-700 ring-emerald-200", icon: "✓" },
  fail: { label: "Fail", badge: "bg-red-50 text-red-700 ring-red-200", icon: "✕" },
  warn: { label: "Warn", badge: "bg-amber-50 text-amber-700 ring-amber-200", icon: "!" },
  info: { label: "Info", badge: "bg-blue-50 text-blue-700 ring-blue-200", icon: "i" },
};

const SEVERITY: Record<ScrutinyCheck["severity"], string> = {
  low: "bg-zinc-100 text-zinc-600",
  medium: "bg-zinc-200 text-zinc-800",
  high: "bg-zinc-800 text-zinc-100",
};

export function CheckList({ checks }: { checks: ScrutinyCheck[] }) {
  return (
    <ul className="divide-y divide-zinc-200 rounded-lg border border-zinc-200 bg-white shadow-card">
      {checks.map((c) => {
        const s = CHECK_STATUS[c.status];
        return (
          <li key={c.checkId} className="p-3">
            <details>
              <summary className="flex cursor-pointer list-none items-center gap-2 [&::-webkit-details-marker]:hidden">
                <span
                  aria-hidden="true"
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${s.badge}`}
                >
                  {s.icon}
                </span>
                <span className="min-w-0 flex-1 truncate text-sm font-medium">
                  <span className="font-mono text-xs text-zinc-400">{c.checkId}</span>{" "}
                  {c.label}
                </span>
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${SEVERITY[c.severity]}`}
                >
                  {c.severity}
                </span>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${s.badge}`}
                >
                  {s.label}
                </span>
              </summary>
              <div className="mt-2 space-y-2 border-l-2 border-zinc-200 pl-3 text-sm">
                <p>
                  <span className="font-semibold text-zinc-700">Evidence: </span>
                  <span className="text-zinc-700">{c.evidence}</span>
                </p>
                <p>
                  <span className="font-semibold text-zinc-700">Why this matters: </span>
                  <span className="text-zinc-700">{c.explanation}</span>
                </p>
              </div>
            </details>
          </li>
        );
      })}
    </ul>
  );
}
