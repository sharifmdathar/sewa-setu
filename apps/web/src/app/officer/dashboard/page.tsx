// B6 — officer metrics dashboard. Cards are 100% getMetrics. Charts use
// MetricsSummary.applicationsByDay / riskDistribution (CR-3) when the server sends
// them, and fall back to the getQueue derivation when absent (see CR-3.md).

import Link from "next/link";
import { getApiClient } from "@/lib/api/client";
import { appsByDay, riskDistribution } from "./data";
import { ApplicationsByDayChart, RiskDistributionChart } from "./charts";

export const dynamic = "force-dynamic";

function Card({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-zinc-400">{hint}</p>}
    </div>
  );
}

export default async function DashboardPage() {
  const api = getApiClient();
  const [metrics, queue] = await Promise.all([api.getMetrics(), api.getQueue()]);
  // getQueue now also returns decided apps; charts keep the pending-only view.
  const pendingQueue = queue.filter((q) => q.status !== "decided");
  // Prefer the contract series (CR-3); fall back to the getQueue derivation.
  const dayData = metrics.applicationsByDay ?? appsByDay(pendingQueue);
  const riskData = metrics.riskDistribution ?? riskDistribution(pendingQueue);
  const avg = metrics.avgScrutinySeconds;
  const avgLabel =
    avg < 0.001
      ? "< 1 ms"
      : avg < 1
        ? `${Math.round(avg * 1000)} ms`
        : `${avg.toFixed(1)} s`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Metrics</h1>
          <p className="text-sm text-zinc-500">
            Generated {new Date(metrics.generatedAt).toLocaleString()}
          </p>
        </div>
        <Link href="/officer" className="text-sm text-zinc-600 underline">
          ← Back to queue
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Card label="Total" value={String(metrics.applicationsTotal)} />
        <Card label="Pending" value={String(metrics.pending)} />
        <Card label="Decided" value={String(metrics.decided)} />
        <Card
          label="Avg scrutiny"
          value={avgLabel}
          hint="target < 60s"
        />
        <Card
          label="Flag rate"
          value={`${Math.round(metrics.flagRate * 100)}%`}
          hint="risk ≥ 60"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ApplicationsByDayChart data={dayData} />
        <RiskDistributionChart data={riskData} />
      </div>

      {(metrics.evalPrecision != null || metrics.evalRecall != null) && (
        <p className="text-xs text-zinc-500">
          Offline eval on dataset-v1 — precision {metrics.evalPrecision?.toFixed(2) ?? "n/a"} ·
          recall {metrics.evalRecall?.toFixed(2) ?? "n/a"} (SPEC §7 gate ≥0.90 / ≥0.85).
        </p>
      )}
    </div>
  );
}
