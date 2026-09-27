// J1 step 3 — upload UI, one card per required docType (contract: file ->
// base64 POST). The contract has no "list documents" endpoint, so this screen
// tracks what *you* uploaded client-side; on reload it starts fresh, which is
// fine for the POC (mock store still accepts re-uploads).

import Link from "next/link";
import { notFound } from "next/navigation";
import { getApiClient } from "@/lib/api/client";
import { UploadPanel } from "./upload-panel";

export const dynamic = "force-dynamic";

export default async function UploadPage({
  params,
}: {
  params: { id: string };
}) {
  const api = getApiClient();
  let application;
  try {
    application = await api.getApplication(params.id);
  } catch {
    notFound();
  }
  const services = await api.listServices();
  const service = services.find((s) => s.id === application.serviceId);
  if (!service) notFound();

  return (
    <div className="max-w-lg space-y-6">
      <div>
        <p className="text-sm text-zinc-500">Step 3 of 4</p>
        <h1 className="text-2xl font-bold">Upload your documents</h1>
        <p className="mt-1 text-sm text-zinc-600">
          For {service.name}, we need: {service.requiredDocTypes.join(", ")}.
          Photos or scans are fine.
        </p>
      </div>
      <UploadPanel applicationId={application.id} docTypes={service.requiredDocTypes} />
      <Link
        href={`/citizen/apps/${application.id}`}
        className="text-sm text-zinc-500 underline"
      >
        Skip to my application status →
      </Link>
    </div>
  );
}
