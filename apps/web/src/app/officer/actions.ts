"use server";

// Officer journey mutation (B4, J3): postDecision then back to the report so
// the citizen-visible timeline update is immediately consistent (mock store).

import { redirect } from "next/navigation";
import { getApiClient } from "@/lib/api/client";
import type { Decision } from "@/lib/api/types";

const DECISIONS: Decision["decision"][] = ["approve", "reject", "request_info"];

export async function postDecisionAction(formData: FormData): Promise<void> {
  const applicationId = String(formData.get("applicationId") ?? "");
  const decisionRaw = String(formData.get("decision") ?? "");
  const officerNotes = String(formData.get("officerNotes") ?? "").trim();
  if (!applicationId || !DECISIONS.includes(decisionRaw as Decision["decision"])) {
    return;
  }
  if (decisionRaw === "reject" && officerNotes === "") {
    // ui-guidelines §2: notes are required for reject.
    redirect(`/officer/apps/${applicationId}?err=notes`);
  }
  await getApiClient().postDecision({
    applicationId,
    decision: decisionRaw as Decision["decision"],
    officerNotes,
  });
  redirect(`/officer/apps/${applicationId}?done=1`);
}
