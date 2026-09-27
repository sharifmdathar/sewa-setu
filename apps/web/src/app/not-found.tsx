// Global 404 (B8): notFound() anywhere in a journey lands here inside the
// shell, phrased for humans with one way back.

import Link from "next/link";
import { EmptyState } from "@/components/EmptyState";

export default function NotFound() {
    return (
        <EmptyState
            title="Page not found"
            description="That page or application doesn't exist. It may have been moved or the link is out of date."
            icon="∅"
            action={
                <Link
                    href="/"
                    className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
                >
                    Back to start
                </Link>
            }
        />
    );
}
