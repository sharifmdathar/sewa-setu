// Segment error boundary (B8): failures in the citizen journey render
// ErrorState + a retry (client reset) — never Next's raw-stack screen.

"use client";

import { ErrorState, errorToMessage } from "@/components/ErrorState";

export default function CitizenError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    return (
        <ErrorState
            title="We couldn't load your application area"
            message={errorToMessage(error)}
            retry={
                <button
                    type="button"
                    onClick={reset}
                    className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white"
                >
                    Try again
                </button>
            }
        />
    );
}
