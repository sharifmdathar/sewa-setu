// Loading skeleton block (ui-guidelines §3): routes show structure while
// async server components fetch, never a blank flash. Presentational only.

function SkeletonLine({ w }: { w: string }) {
    return (
        <div
            aria-hidden="true"
            className={`h-4 animate-pulse rounded bg-zinc-200 ${w}`}
        />
    );
}

/** A few shimmering lines standing in for a card/list/table. */
export function Skeleton({ rows = 4 }: { rows?: number }) {
    return (
        <div
            role="status"
            aria-label="Loading"
            className="space-y-3 rounded-lg border border-zinc-200 bg-white p-5 shadow-card"
        >
            <SkeletonLine w="w-1/3" />
            {Array.from({ length: rows }, (_, i) => (
                <SkeletonLine key={i} w={i % 2 === 0 ? "w-5/6" : "w-2/3"} />
            ))}
            <span className="sr-only">Loading…</span>
        </div>
    );
}
