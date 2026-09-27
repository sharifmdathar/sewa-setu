// J1 step 1 — browse services (citizen pole: whole card is the one action).

import Link from "next/link";
import { getApiClient } from "@/lib/api/client";

export const dynamic = "force-dynamic"; // mock store is per-process in-memory

export default async function CitizenHomePage() {
  const services = await getApiClient().listServices();
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Apply for a certificate</h1>
        <p className="mt-1 text-sm text-zinc-600">
          Choose a service to start. You will upload documents and track status here.
        </p>
      </div>
      <ul className="grid gap-4 sm:grid-cols-2">
        {services.map((s) => (
          <li key={s.id}>
            <Link
              href={`/citizen/services/${s.id}/apply`}
              className="block min-h-12 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm transition hover:border-brand-500 hover:shadow-card"
            >
              <span className="block text-lg font-semibold">{s.name}</span>
              <span className="mt-1 block text-sm text-zinc-500">
                Documents needed: {s.requiredDocTypes.join(", ")}
              </span>
              <span className="mt-3 inline-block rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white">
                Apply now
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
