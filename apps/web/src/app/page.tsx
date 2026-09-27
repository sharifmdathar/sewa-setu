import Link from "next/link";

// Landing = a neutral role chooser. Deliberately no data fetch (so it stays
// static and never hits the API at build time) and no raw "catalog smoke test"
// block — that belongs in /dev/components, not the front door.

const ROLES = [
  {
    href: "/citizen",
    title: "Citizen",
    desc: "Apply for a certificate, upload your documents, and track your application status in one place.",
    cta: "Start an application",
  },
  {
    href: "/officer",
    title: "Officer",
    desc: "Review the risk-ranked queue, read explainable scrutiny reports, and record the decision.",
    cta: "Open the review queue",
  },
];

export default function Home() {
  return (
    <div className="mx-auto w-full max-w-3xl py-10">
      <header className="text-center">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Sewa Setu
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-zinc-600">
          Agentic application scrutiny &amp; document verification. The agent
          recommends; the officer decides — with an explanation behind every
          check.
        </p>
      </header>

      <div className="mt-10 grid gap-4 sm:grid-cols-2">
        {ROLES.map((r) => (
          <Link
            key={r.href}
            href={r.href}
            className="group flex flex-col rounded-xl border border-zinc-200 bg-white p-6 shadow-card transition hover:border-brand-500 hover:shadow-lg"
          >
            <span className="text-lg font-semibold">{r.title}</span>
            <span className="mt-2 flex-1 text-sm text-zinc-600">{r.desc}</span>
            <span className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand-700">
              {r.cta}
              <span
                aria-hidden="true"
                className="transition-transform group-hover:translate-x-0.5"
              >
                →
              </span>
            </span>
          </Link>
        ))}
      </div>

      <p className="mt-10 text-center text-xs text-zinc-400">
        POC · synthetic data only · no real PII
      </p>
    </div>
  );
}
