"use server";

// Citizen journey mutations (B3, J1): create -> upload docs -> run scrutiny.
// Server actions only touch ApiClient + redirect (AGENTS.md: data via ApiClient).

import { redirect } from "next/navigation";
import { getApiClient } from "@/lib/api/client";
import { fieldsFromFormData, parseFieldSchema } from "@/lib/fields";

export async function createApplicationAction(formData: FormData): Promise<void> {
  const serviceId = String(formData.get("serviceId") ?? "");
  if (!serviceId) throw new Error("Missing serviceId");
  const api = getApiClient();
  const services = await api.listServices();
  const service = services.find((s) => s.id === serviceId);
  if (!service) throw new Error(`Unknown service ${serviceId}`);
  const fields = parseFieldSchema(service.fieldSchema);
  const application = await api.createApplication({
    serviceId,
    applicantFields: fieldsFromFormData(formData, fields),
  });
  redirect(`/citizen/apps/${application.id}/upload`);
}

export async function uploadDocumentAction(
  fdOrArgs: FormData | { applicationId: string; docType: string; fileName: string; contentBase64: string },
): Promise<void> {
  let applicationId: string;
  let docType: string;
  let fileName: string;
  let contentBase64: string;
  if (fdOrArgs instanceof FormData) {
    // Progressive-enhancement path: plain <form method="post">, file control.
    applicationId = String(fdOrArgs.get("applicationId") ?? "");
    docType = String(fdOrArgs.get("docType") ?? "");
    const file = fdOrArgs.get("file");
    if (!(file instanceof File)) return;
    fileName = file.name;
    contentBase64 = Buffer.from(await file.arrayBuffer()).toString("base64");
  } else {
    ({ applicationId, docType, fileName, contentBase64 } = fdOrArgs);
  }
  if (!applicationId || !docType) return;
  await getApiClient().uploadDocument(applicationId, {
    docType,
    fileName,
    contentBase64,
  });
}

export async function runScrutinyAction(
  fdOrId: FormData | { applicationId: string },
): Promise<void> {
  const applicationId =
    fdOrId instanceof FormData
      ? String(fdOrId.get("applicationId") ?? "")
      : fdOrId.applicationId;
  if (!applicationId) return;
  await getApiClient().runScrutiny(applicationId);
  redirect(`/citizen/apps/${applicationId}`);
}
