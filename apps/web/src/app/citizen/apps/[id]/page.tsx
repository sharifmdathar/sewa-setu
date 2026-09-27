// J1 step 4 + J4 — citizen timeline for one application (getApplication only).

import Link from "next/link";
import { notFound } from "next/navigation";
import { getApiClient } from "@/lib/api/client";
import { StatusBadge } from "@/components/StatusBadge";
import { formatFieldValue, parseFieldSchema } from "@/lib/fields";
import { StatusFeed } from "./status-feed";

export const dynamic = "force-dynamic";

const NEXT_STEP: Record<string, string> = {
  submitted: "Next: upload your documents.",
  documents_uploaded: "Next: run the automatic checks.",
  scrutiny_pending: "Your documents are being checked. This usually takes under a minute.",
  scrutiny_done: "Checks are done. An officer will review your application shortly.",
  decided: "A decision has been made — see the latest update below.",
  info_requested: "We need something more from you — see the latest update below.",
};

export default async function TimelinePage({
  params,
}: {
  params: { id: string };
}) {
  const api = getApiClient();
  let application;
  try {
    application = await api.getApplication(params.id);
  } catch {
    notFound();
  }
  const services = await api.listServices();
  const service = services.find((s) => s.id === application.serviceId);
  const fields = parseFieldSchema(service?.fieldSchema);

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <p className="text-sm text-zinc-500">Step 4 of 4</p>
        <div className="mt-1 flex items-center justify-between gap-3">
          <h1 className="text-2xl font-bold">
            {service?.name ?? "Application"} <span className="font-mono text-base text-zinc-400">#{application.id}</span>
          </h1>
          <StatusBadge status={application.status} />
        </div>
        <p className="mt-2 rounded-md bg-blue-50 px-4 py-3 text-sm text-blue-900" aria-live="polite">
          {NEXT_STEP[application.status]}
        </p>
      </div>

      <section className="rounded-lg border border-zinc-200 bg-white p-5">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
          What you applied with
        </h2>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          {fields.map(({ name, def }) => (
            <div key={name} className="contents">
              <dt className="text-zinc-500">{def.label}</dt>
              <dd className="font-medium">
                {formatFieldValue(application.applicantFields[name])}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <StatusFeed applicationId={application.id} initial={application.timeline} />

      <div className="flex gap-4 text-sm">
        <Link href="/citizen" className="underline text-zinc-600">
          Apply for another service
        </Link>
        <Link href="/citizen/apps" className="underline text-zinc-600">
          My applications
        </Link>
      </div>
    </div>
  );
}
