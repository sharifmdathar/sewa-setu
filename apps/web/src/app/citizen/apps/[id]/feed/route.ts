// BFF route for the citizen status feed (B5). Server-side: reads through
// ApiClient (never exposed to the browser) and returns just what the poller
// needs. Separate URL segment from page.tsx, so no route conflict.

import { NextResponse } from "next/server";
import { getApiClient } from "@/lib/api/client";

export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  { params }: { params: { id: string } },
): Promise<NextResponse> {
  const api = getApiClient();
  try {
    const app = await api.getApplication(params.id);
    return NextResponse.json(
      { status: app.status, timeline: app.timeline },
      { headers: { "cache-control": "no-store" } },
    );
  } catch {
    return NextResponse.json({ error: "not_found" }, { status: 404 });
  }
}
