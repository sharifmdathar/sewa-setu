"use client";

// Recharts is isolated to this client component under officer/dashboard/** only
// (see docs/track-b/deps.md). Server passes plain arrays so the charts stay
// presentational.

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { BAND_LABEL, type BandCount, type DayCount } from "./data";

const BAND_COLOR: Record<BandCount["band"], string> = {
  low: "#10b981", // emerald-500
  medium: "#f59e0b", // amber-500
  high: "#ef4444", // red-500
};

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4">
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
        {title}
      </h2>
      <div className="h-64 w-full">{children}</div>
    </section>
  );
}

export function RiskDistributionChart({ data }: { data: BandCount[] }) {
  return (
    <ChartCard title="Applications by risk band">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" vertical={false} />
          <XAxis dataKey="band" tickFormatter={(b) => BAND_LABEL[b as BandCount["band"]]} fontSize={12} stroke="#71717a" />
          <YAxis allowDecimals={false} fontSize={12} stroke="#71717a" />
          <Tooltip
            formatter={(v: unknown) => [String(v), "apps"]}
            labelFormatter={(b) => BAND_LABEL[b as BandCount["band"]]}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
            {data.map((d) => (
              <Cell key={d.band} fill={BAND_COLOR[d.band]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

export function ApplicationsByDayChart({ data }: { data: DayCount[] }) {
  return (
    <ChartCard title="Applications activity (by day)">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e4e4e7" vertical={false} />
          <XAxis dataKey="date" tickFormatter={(d: string) => d.slice(5)} fontSize={12} stroke="#71717a" />
          <YAxis allowDecimals={false} fontSize={12} stroke="#71717a" />
          <Tooltip formatter={(v: unknown) => [String(v), "apps"]} />
          <Bar dataKey="count" fill="#18181b" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
