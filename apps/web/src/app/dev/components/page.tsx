// Storybook-less component gallery (B2 DoD). Server component; demo data is
// shaped strictly by contract types — fixtures reused where possible, literals
// elsewhere so every enum value is visible on one page.

import { CheckList } from "@/components/CheckList";
import { EmptyState } from "@/components/EmptyState";
import { ErrorState } from "@/components/ErrorState";
import { RiskMeter } from "@/components/RiskMeter";
import { RoleSwitcher } from "@/components/RoleSwitcher";
import { StatusBadge } from "@/components/StatusBadge";
import { seedStore } from "@/lib/api/fixtures";
import type { AppStatus, ScrutinyCheck } from "@/lib/api/types";

const ALL_STATUSES: AppStatus[] = [
  "submitted",
  "documents_uploaded",
  "scrutiny_pending",
  "scrutiny_done",
  "decided",
  "info_requested",
];

const INFO_CHECK: ScrutinyCheck = {
  checkId: "C0",
  label: "Application window",
  status: "info",
  severity: "low",
  evidence: "Service opens for applications year-round (mock notice).",
  explanation: "Informational note; nothing to fix.",
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
        {title}
      </h2>
      {children}
    </section>
  );
}

export default function DevComponentsPage() {
  const store = seedStore();
  const mixedChecks: ScrutinyCheck[] = [
    ...store.reportsByApp["app-1002"]!.checks, // pass + fail mix
    INFO_CHECK,
    ...store.reportsByApp["app-1004"]!.checks.slice(0, 1), // C3 fail (missing doc)
  ];

  return (
    <div className="space-y-10">
      <h1 className="text-2xl font-bold">/dev/components — UI kit gallery</h1>

      <Section title="Shell · RoleSwitcher (also in header)">
        <RoleSwitcher />
      </Section>

      <Section title="StatusBadge · all contract AppStatus values">
        <div className="flex flex-wrap items-center gap-2">
          {ALL_STATUSES.map((s) => (
            <StatusBadge key={s} status={s} />
          ))}
        </div>
      </Section>

      <Section title="RiskMeter · bands low <30 / medium 30–59 / high ≥60">
        <div className="space-y-1">
          <RiskMeter score={8} showLabel />
          <RiskMeter score={29} showLabel />
          <RiskMeter score={30} showLabel />
          <RiskMeter score={55} showLabel />
          <RiskMeter score={60} showLabel />
          <RiskMeter score={95} showLabel />
        </div>
      </Section>

      <Section title="CheckList · C1–C5 with severity + expandable evidence/explanation">
        <CheckList checks={mixedChecks} />
      </Section>

      <Section title="EmptyState · one next action">
        <EmptyState
          title="No applications yet"
          description="Pick a service to start your first application."
          action={
            <span className="inline-flex min-h-12 items-center rounded-md bg-brand-600 px-5 py-3 text-sm font-medium text-white">
              Browse services
            </span>
          }
        />
      </Section>

      <Section title="ErrorState · message + retry">
        <ErrorState
          title="Couldn’t load the queue"
          message="The scrutiny service didn’t respond. Please try again."
          retry={
            <span className="inline-flex min-h-12 items-center rounded-md border border-red-300 bg-white px-5 py-3 text-sm font-medium text-red-700">
              Retry
            </span>
          }
        />
      </Section>
    </div>
  );
}
