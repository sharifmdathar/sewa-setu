// "My applications" index. The frozen contract has no list-my-applications
// endpoint, so this derives the list from getQueue (excludes decided apps —
// accepted for the POC; citizens also always have their direct timeline link).

import Link from "next/link";
import { getApiClient } from "@/lib/api/client";
import { EmptyState } from "@/components/EmptyState";
import { StatusBadge } from "@/components/StatusBadge";

export const dynamic = "force-dynamic";

export default async function MyApplicationsPage() {
  const api = getApiClient();
  const [queue, services] = [await api.getQueue(), await api.listServices()];
  const nameOf = (id: string) =>
    services.find((s) => s.id === id)?.name ?? id;

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <h1 className="text-2xl font-bold">My applications</h1>
      {queue.length === 0 ? (
        <EmptyState
          title="No open applications"
          description="When you apply for a service, it will show up here."
          action={
            <Link
              href="/citizen"
              className="inline-flex min-h-12 items-center rounded-md bg-zinc-900 px-5 py-3 text-sm font-medium text-white"
            >
              Browse services
            </Link>
          }
        />
      ) : (
        <ul className="space-y-3">
          {queue.map((q) => (
            <li key={q.applicationId}>
              <Link
                href={`/citizen/apps/${q.applicationId}`}
                className="flex min-h-12 items-center justify-between gap-3 rounded-lg border border-zinc-200 bg-white p-4 hover:border-zinc-900"
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">
                    {nameOf(q.serviceId)}
                  </span>
                  <span className="font-mono text-xs text-zinc-400">
                    #{q.applicationId}
                  </span>
                </span>
                <StatusBadge status={q.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
