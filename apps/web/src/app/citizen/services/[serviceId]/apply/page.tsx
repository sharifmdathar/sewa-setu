// J1 step 2 — dynamic application form built from Service.fieldSchema.

import Link from "next/link";
import { notFound } from "next/navigation";
import { getApiClient } from "@/lib/api/client";
import { parseFieldSchema } from "@/lib/fields";
import { ApplyForm } from "./apply-form";

export const dynamic = "force-dynamic";

export default async function ApplyPage({
  params,
}: {
  params: { serviceId: string };
}) {
  const services = await getApiClient().listServices();
  const service = services.find((s) => s.id === params.serviceId);
  if (!service) notFound();
  const fields = parseFieldSchema(service.fieldSchema);

  return (
    <div className="max-w-lg space-y-6">
      <div>
        <p className="text-sm text-zinc-500">Step 2 of 4</p>
        <h1 className="text-2xl font-bold">Apply for {service.name}</h1>
        <p className="mt-1 text-sm text-zinc-600">
          Fill in your details exactly as they appear on your documents.
        </p>
      </div>
      <ApplyForm serviceId={service.id} fields={fields} />
      <Link href="/citizen" className="text-sm text-zinc-500 underline">
        ← Back to services
      </Link>
    </div>
  );
}
