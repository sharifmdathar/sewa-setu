// J3 — scrutiny report for one application: every check with status, severity,
// evidence + explanation (never hidden), extracted fields vs declared fields,
// recommendation + modelMeta, decision panel (approve / reject / request_info).

import Link from "next/link";
import { notFound } from "next/navigation";
import { getApiClient } from "@/lib/api/client";
import { CheckList } from "@/components/CheckList";
import { RiskMeter } from "@/components/RiskMeter";
import { StatusBadge } from "@/components/StatusBadge";
import { formatFieldValue } from "@/lib/fields";
import type { ScrutinyReport } from "@/lib/api/types";
import { DecisionPanel } from "./decision-panel";

export const dynamic = "force-dynamic";

const RECO_STYLE: Record<ScrutinyReport["recommendation"], string> = {
  approve: "bg-emerald-50 text-emerald-900 border-emerald-200",
  request_info: "bg-amber-50 text-amber-900 border-amber-200",
  manual_review: "bg-blue-50 text-blue-900 border-blue-200",
  reject: "bg-red-50 text-red-900 border-red-200",
};

function textOf(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/**
 * Says out loud whether a model read this document, and which one.
 *
 * `modelMeta.extractor` names the *component* ("template" or "llm-vlm"); the served model is in
 * `versions`, where "code" means no endpoint was involved. Without this line an officer (or a
 * judge) cannot tell the rules-only path from a live model read, and the two have very
 * different accuracy - which is the same distinction the eval reports title themselves with.
 */
function provenanceLabel(meta: ScrutinyReport["modelMeta"]): string {
  const versions = meta.versions ?? {};
  const served = textOf(versions.extractor);
  const rules = textOf(versions.rules);
  const parts = [
    served && served !== "code" ? `model ${served}` : "no model in the loop",
  ];
  if (rules) parts.push(`rules v${rules.replace(/^v/, "")}`);
  return parts.join(" · ");
}

export default async function OfficerReportPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams: { done?: string; err?: string };
}) {
  const api = getApiClient();
  let application;
  try {
    application = await api.getApplication(params.id);
  } catch {
    notFound();
  }
  const report = await api.getScrutiny(application.id);
  const services = await api.listServices();
  const service = services.find((s) => s.id === application.serviceId);
  const decided = application.status === "decided" || application.status === "info_requested";

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-xl font-bold">
              {service?.name ?? "Application"}{" "}
              <span className="font-mono text-sm text-zinc-400">#{application.id}</span>
            </h1>
            <p className="text-sm text-zinc-500">
              {typeof application.applicantFields["applicantName"] === "string"
                ? (application.applicantFields["applicantName"] as string)
                : "Unknown applicant"}{" "}
              · created {new Date(application.createdAt).toLocaleString()}
            </p>
          </div>
          <StatusBadge status={application.status} />
        </div>

        {searchParams.done && (
          <p className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-900">
            Decision recorded — the citizen timeline is updated.
          </p>
        )}
        {searchParams.err === "notes" && (
          <p role="alert" className="rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800">
            Officer notes are required when rejecting.
          </p>
        )}

        {!report ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-5 text-sm text-amber-900">
            Scrutiny has not been run for this application yet. The citizen
            needs to upload documents and run the automatic checks first.
          </div>
        ) : (
          <>
            <section className="flex flex-wrap items-center gap-6 rounded-lg border border-zinc-200 bg-white p-4">
              <div>
                <p className="text-xs uppercase tracking-wide text-zinc-500">Risk</p>
                <RiskMeter score={report.riskScore} showLabel />
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-zinc-500">
                  Agent recommendation
                </p>
                <span
                  className={`mt-1 inline-block rounded-md border px-2.5 py-1 text-sm font-semibold ${RECO_STYLE[report.recommendation]}`}
                >
                  {report.recommendation}
                </span>
              </div>
              <div className="ml-auto text-right text-xs text-zinc-400">
                <p>
                  generated {new Date(report.generatedAt).toLocaleString()}
                </p>
                <p>
                  {report.modelMeta.extractor ?? "?"} / {report.modelMeta.adjudicator ?? "?"} ·{" "}
                  {report.modelMeta.latencyMs ?? "?"} ms
                </p>
                <p>{provenanceLabel(report.modelMeta)}</p>
              </div>
            </section>

            <section className="space-y-2">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Checks (C1–C5)
              </h2>
              <CheckList checks={report.checks} />
            </section>

            <section className="rounded-lg border border-zinc-200 bg-white p-4">
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Declared vs extracted fields
              </h2>
              <table className="w-full text-left text-sm">
                <thead className="text-xs uppercase text-zinc-400">
                  <tr>
                    <th className="py-1 pr-3">Field</th>
                    <th className="py-1 pr-3">Declared</th>
                    <th className="py-1">Extracted</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {Array.from(
                    new Set([
                      ...Object.keys(application.applicantFields),
                      ...Object.keys(report.extractedFields),
                    ]),
                  ).map((k) => {
                    const declared = application.applicantFields[k];
                    const extracted = report.extractedFields[k];
                    const clash =
                      JSON.stringify(declared) !== JSON.stringify(extracted);
                    return (
                      <tr key={k}>
                        <td className="py-1.5 pr-3 font-mono text-xs text-zinc-500">{k}</td>
                        <td className={`py-1.5 pr-3 ${clash ? "font-semibold text-red-700" : ""}`}>
                          {formatFieldValue(declared)}
                        </td>
                        <td className={`py-1.5 ${clash ? "font-semibold text-red-700" : ""}`}>
                          {formatFieldValue(extracted)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </section>
          </>
        )}
      </div>

      <aside className="space-y-4 lg:sticky lg:top-16 lg:self-start">
        <DecisionPanel applicationId={application.id} disabled={decided} />
        <details className="rounded-lg border border-zinc-200 bg-white p-3 text-xs text-zinc-500">
          <summary className="cursor-pointer font-medium">Raw timeline</summary>
          <ol className="mt-2 space-y-1.5">
            {application.timeline.map((ev, i) => (
              <li key={i}>
                {new Date(ev.at).toLocaleString()} — {ev.actor}: {ev.message}
              </li>
            ))}
          </ol>
        </details>
        <Link href="/officer" className="block text-sm text-zinc-500 underline">
          ← Back to queue
        </Link>
      </aside>
    </div>
  );
}
