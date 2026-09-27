// Client-safe helpers for the citizen status feed (B5). No server-only imports
// here; the actual data comes from our own BFF route (which uses ApiClient),
// so components never touch the backend API directly (AGENTS.md).

import type { AppStatus, TimelineEvent } from "@/lib/api/types";

export interface FeedResponse {
  status: AppStatus;
  timeline: TimelineEvent[];
}

/** Stable identity for a timeline event (contract has no id on TimelineEvent). */
export function eventKey(e: TimelineEvent): string {
  return `${e.at}|${e.actor}|${e.event}|${e.message}`;
}

/** Events present in `next` but not `prev`, limited to officer/system actors. */
export function newNotifications(
  prev: TimelineEvent[],
  next: TimelineEvent[],
): TimelineEvent[] {
  const seen = new Set(prev.map(eventKey));
  return next.filter(
    (e) => !seen.has(eventKey(e)) && (e.actor === "officer" || e.actor === "system"),
  );
}

/** Poll the per-application feed via the BFF route handler. */
export async function fetchFeed(applicationId: string): Promise<FeedResponse | null> {
  const res = await fetch(`/citizen/apps/${applicationId}/feed`, { cache: "no-store" });
  if (!res.ok) return null;
  return (await res.json()) as FeedResponse;
}
