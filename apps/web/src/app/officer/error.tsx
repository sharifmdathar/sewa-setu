// Segment error boundary (B8) for the officer journey.

"use client";

import { ErrorState, errorToMessage } from "@/components/ErrorState";

export default function OfficerError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    return (
        <ErrorState
            title="The officer console hit an error"
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
