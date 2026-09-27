// J3 — officer queue: riskScore desc (mock already sorts), no-JS GET filters.
// Density pole (ui-guidelines §2).

import Link from "next/link";
import { getApiClient } from "@/lib/api/client";
import { EmptyState } from "@/components/EmptyState";
import { RiskMeter } from "@/components/RiskMeter";
import { StatusBadge } from "@/components/StatusBadge";
import { StatusFilter } from "./status-filter";
import type { AppStatus } from "@/lib/api/types";

export const dynamic = "force-dynamic";

// All contract statuses (AppStatus enum). "decided" is offered as a filter but
// left unchecked by default, so the queue opens on open work only.
const STATUS_OPTIONS: AppStatus[] = [
  "submitted",
  "documents_uploaded",
  "scrutiny_pending",
  "scrutiny_done",
  "info_requested",
  "decided",
];
const DEFAULT_STATUSES: AppStatus[] = STATUS_OPTIONS.filter(
  (s) => s !== "decided",
);

function nameOf(fields: Record<string, unknown>): string {
  const n = fields["applicantName"];
  return typeof n === "string" && n ? n : "—";
}

export default async function OfficerQueuePage({
  searchParams,
}: {
  searchParams: { status?: string | string[]; risk?: string; f?: string };
}) {
  const api = getApiClient();
  const queue = await api.getQueue();
  const services = await api.listServices();
  const nameOfService = (id: string) =>
    services.find((s) => s.id === id)?.name ?? id;

  // Applicant names come from each application (queue item has no fields).
  const rows = [];
  for (const q of queue) {
    try {
      const app = await api.getApplication(q.applicationId);
      rows.push({ q, applicant: nameOf(app.applicantFields) });
    } catch {
      /* app vanished mid-render — skip */
    }
  }

  // Multi-select status filter. `f=1` marks an explicit form submission so we
  // can tell "user unchecked everything" (show none) apart from a first load
  // (default = every status except decided).
  const explicit = searchParams.f === "1";
  const raw = searchParams.status;
  const chosen = (Array.isArray(raw) ? raw : raw ? [raw] : []).filter(
    (s): s is AppStatus => (STATUS_OPTIONS as string[]).includes(s),
  );
  const selectedStatuses = explicit ? chosen : DEFAULT_STATUSES;
  const selected = new Set<AppStatus>(selectedStatuses);
  const risk =
    searchParams.risk === "high" || searchParams.risk === "low"
      ? searchParams.risk
      : undefined;
  const filtered = rows.filter(({ q }) => {
    if (!selected.has(q.status)) return false;
    if (risk === "high" && q.riskScore < 60) return false;
    if (risk === "low" && q.riskScore >= 60) return false;
    return true;
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Review queue</h1>
          <p className="text-sm text-zinc-500">
            Sorted by risk (highest first) · {filtered.length} of {rows.length} shown
          </p>
        </div>
        <form
          method="get"
          className="flex items-center gap-2 text-sm"
        >
          <input type="hidden" name="f" value="1" />
          <StatusFilter options={STATUS_OPTIONS} selected={selectedStatuses} />
          <label htmlFor="f-risk" className="sr-only">
            Filter by risk
          </label>
          <select
            id="f-risk"
            name="risk"
            defaultValue={risk ?? ""}
            className="min-h-10 rounded-md border border-zinc-300 bg-white px-2"
          >
            <option value="">All risk</option>
            <option value="high">High (≥60)</option>
            <option value="low">Low (&lt;60)</option>
          </select>
          <button className="min-h-10 rounded-md bg-zinc-900 px-4 font-medium text-white">
            Filter
          </button>
        </form>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          title="No applications match"
          description="Clear the filters to see the full queue."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-2">Application</th>
                <th className="px-3 py-2">Applicant</th>
                <th className="px-3 py-2">Service</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Risk</th>
                <th className="px-3 py-2">Updated</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {filtered.map(({ q, applicant }) => (
                <tr key={q.applicationId} className="hover:bg-zinc-50">
                  <td className="px-3 py-2 font-mono text-xs">#{q.applicationId}</td>
                  <td className="px-3 py-2 font-medium">{applicant}</td>
                  <td className="px-3 py-2">{nameOfService(q.serviceId)}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={q.status} />
                  </td>
                  <td className="px-3 py-2">
                    <RiskMeter score={q.riskScore} />
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-xs text-zinc-500">
                    {new Date(q.updatedAt).toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <Link
                      href={`/officer/apps/${q.applicationId}`}
                      className="inline-block rounded-md border border-zinc-300 px-3 py-1.5 font-medium hover:border-zinc-900"
                    >
                      Open report
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
