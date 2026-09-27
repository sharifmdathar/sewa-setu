import { api, apiMode } from "@/lib/api/client";
import type { Service } from "@/lib/api/types";

export default async function Home() {
  const services = await api.listServices();
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-10">
      <h1 className="text-4xl font-bold tracking-tight">
        Sewa Setu Scrutiny POC
      </h1>
      <p className="max-w-md text-center text-zinc-600">
        Agentic application scrutiny &amp; document verification — citizen and
        officer workbench.
      </p>
      <Catalog services={services} />
    </main>
  );
}

/** Server-rendered smoke test that the ApiClient + mock transport work. */
function Catalog({ services }: { services: Service[] }) {
  return (
    <section className="w-full max-w-lg rounded-lg border border-zinc-200 p-6">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
        Service catalog ({apiMode()} mode, {services.length} services)
      </h2>
      <ul className="space-y-2">
        {services.map((s) => (
          <li key={s.id} className="flex items-baseline justify-between">
            <span className="font-medium">{s.name}</span>
            <span className="text-sm text-zinc-500">
              {s.requiredDocTypes.join(", ")}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
