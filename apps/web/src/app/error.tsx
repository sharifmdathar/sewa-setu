// Root error boundary (B8): covers the landing page and anything outside
// the two journey segments (which have their own).

"use client";

import { ErrorState, errorToMessage } from "@/components/ErrorState";

export default function RootError({
    error,
    reset,
}: {
    error: Error & { digest?: string };
    reset: () => void;
}) {
    return (
        <ErrorState
            title="Something went wrong"
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
