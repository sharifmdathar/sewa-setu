// Pure, component-free derivations for the officer dashboard (B6).
// Cards come straight from MetricsSummary; the two charts are derived here from
// QueueItem[] as the CR-1 stopgap (see docs/change-requests/CR-1.md).

import type { QueueItem } from "@/lib/api/types";
import { riskBand, type RiskBand } from "@/components/RiskMeter";

export interface DayCount {
  date: string; // YYYY-MM-DD
  count: number;
}
export interface BandCount {
  band: RiskBand;
  count: number;
}

const BAND_ORDER: RiskBand[] = ["low", "medium", "high"];

/** Count applications whose updatedAt falls on each calendar day (UTC). */
export function appsByDay(queue: QueueItem[]): DayCount[] {
  const counts = new Map<string, number>();
  for (const q of queue) {
    const day = q.updatedAt.slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) continue;
    counts.set(day, (counts.get(day) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([date, count]) => ({ date, count }))
    .sort((a, b) => (a.date < b.date ? -1 : 1));
}

/** Bucket riskScore into low/medium/high bands (every band present, even if 0). */
export function riskDistribution(queue: QueueItem[]): BandCount[] {
  const counts: Record<RiskBand, number> = { low: 0, medium: 0, high: 0 };
  for (const q of queue) counts[riskBand(q.riskScore)] += 1;
  return BAND_ORDER.map((band) => ({ band, count: counts[band] }));
}

export const BAND_LABEL: Record<RiskBand, string> = {
  low: "Low (<30)",
  medium: "Medium (30–59)",
  high: "High (≥60)",
};
