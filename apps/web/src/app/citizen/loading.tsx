// Route-segment loading boundary (B8): while the async page fetches mock
// data, the segment shows a skeleton instead of a blank/flash. One per
// top-level journey area; nested segments inherit this boundary.

import { Skeleton } from "@/components/Skeleton";

export default function CitizenLoading() {
    return <Skeleton rows={5} />;
}
