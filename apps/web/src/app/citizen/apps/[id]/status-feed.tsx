"use client";

// B5 — in-app status feed for one application. Polls the BFF feed route every
// 30 s while open, diffs the timeline, and banners new officer/system events.
// Also refreshes when the tab regains focus (helps the officer->citizen demo).
// No push/email (per task). Server seeds `initial` so first paint has content.

import { useEffect, useRef, useState } from "react";
import type { TimelineEvent } from "@/lib/api/types";
import { fetchFeed, newNotifications } from "@/lib/feed";

const POLL_MS = 30_000;

function actorIcon(actor: TimelineEvent["actor"]): string {
  if (actor === "officer") return "👤";
  if (actor === "system") return "⚙";
  return "🙋";
}

export function StatusFeed({
  applicationId,
  initial,
}: {
  applicationId: string;
  initial: TimelineEvent[];
}) {
  const [events, setEvents] = useState<TimelineEvent[]>(initial);
  const [banner, setBanner] = useState<TimelineEvent | null>(null);
  const eventsRef = useRef(events);
  eventsRef.current = events;

  useEffect(() => {
    let active = true;

    async function tick() {
      const data = await fetchFeed(applicationId);
      if (!active || !data) return;
      const fresh = newNotifications(eventsRef.current, data.timeline);
      if (fresh.length > 0) {
        setEvents(data.timeline);
        setBanner(fresh[fresh.length - 1]);
      }
    }

    const id = setInterval(tick, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void tick();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [applicationId]);

  return (
    <section aria-label="Status updates">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Updates
        </h2>
        <span className="inline-flex items-center gap-1.5 text-xs text-zinc-400">
          <span aria-hidden="true" className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
          live · checks every 30s
        </span>
      </div>

      {banner && (
        <div
          role="status"
          aria-live="polite"
          className="mb-3 flex items-start justify-between gap-3 rounded-lg border border-blue-300 bg-blue-50 px-4 py-3 text-sm text-blue-900"
        >
          <span>
            <span className="font-semibold">New update: </span>
            {banner.message}
          </span>
          <button
            type="button"
            onClick={() => setBanner(null)}
            aria-label="Dismiss update"
            className="shrink-0 rounded px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100"
          >
            Dismiss
          </button>
        </div>
      )}

      <ol className="space-y-3">
        {[...events].reverse().map((ev, i) => (
          <li
            key={`${ev.at}-${ev.event}-${i}`}
            className="flex gap-3 rounded-lg border border-zinc-200 bg-white p-4"
          >
            <span aria-hidden="true" className="text-lg">
              {actorIcon(ev.actor)}
            </span>
            <div className="min-w-0">
              <p className="text-sm">{ev.message}</p>
              <p className="mt-0.5 text-xs text-zinc-400">
                {new Date(ev.at).toLocaleString()} · {ev.actor}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
