"use client";

// Client half of J1 step 3: file -> base64 -> uploadDocumentAction, then the
// single primary action "Check my application" -> runScrutinyAction -> timeline.

import { useMemo, useState, useTransition } from "react";
import { runScrutinyAction, uploadDocumentAction } from "../../../actions";

function readFileBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? "");
      resolve(result.split(",")[1] ?? ""); // strip data:…;base64, prefix
    };
    reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
    reader.readAsDataURL(file);
  });
}

export function UploadPanel({
  applicationId,
  docTypes,
}: {
  applicationId: string;
  docTypes: string[];
}) {
  const [uploaded, setUploaded] = useState<string[]>([]);
  const [fileName, setFileName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pending, startTransition] = useTransition();

  const current = useMemo(
    () => docTypes.find((t) => !uploaded.includes(t)),
    [docTypes, uploaded],
  );
  const allDone = current === undefined;

  function onPick(e: React.ChangeEvent<HTMLInputElement>) {
    setError(null);
    setFileName(e.target.files?.[0]?.name ?? null);
  }

  function uploadCurrent() {
    if (!current || !fileName) return;
    const fileInput = document.getElementById(
      `file-${current}`,
    ) as HTMLInputElement | null;
    const file = fileInput?.files?.[0];
    if (!file) return;
    const docType = current;
    setBusy(true);
    void readFileBase64(file)
      .then((contentBase64) =>
        uploadDocumentAction({ applicationId, docType, fileName: file.name, contentBase64 }),
      )
      .then(() => {
        setUploaded((u) => [...u, docType]);
        setFileName(null);
        const input = document.getElementById(`file-${docType}`) as HTMLInputElement | null;
        if (input) input.value = "";
      })
      .catch((err: unknown) =>
        setError(`Upload failed: ${err instanceof Error ? err.message : "please try again"}.`),
      )
      .finally(() => setBusy(false));
  }

  return (
    <div className="space-y-4">
      <ol className="space-y-1 text-sm text-zinc-500" aria-label="Progress">
        {docTypes.map((t) => (
          <li key={t}>
            {uploaded.includes(t) ? "✓" : "○"} {t}
            {uploaded.includes(t) ? " — uploaded" : ""}
          </li>
        ))}
      </ol>

      {!allDone ? (
        <div className="space-y-3 rounded-lg border border-zinc-200 bg-white p-6">
          <label
            htmlFor={`file-${current}`}
            className="block text-base font-semibold"
          >
            Upload your {current}
          </label>
          <input
            id={`file-${current}`}
            type="file"
            accept="image/*,.pdf,.txt"
            onChange={onPick}
            className="block min-h-12 w-full text-sm file:mr-3 file:min-h-12 file:rounded-md file:border-0 file:bg-zinc-100 file:px-4 file:py-3 file:text-sm file:font-medium"
          />
          {error && (
            <p role="alert" className="text-sm text-red-700">
              {error}
            </p>
          )}
          <button
            type="button"
            onClick={uploadCurrent}
            disabled={!fileName || busy}
            className="min-h-12 w-full rounded-md bg-zinc-900 px-5 py-3 text-base font-semibold text-white hover:bg-zinc-700 disabled:opacity-50"
          >
            {busy ? "Uploading…" : `Upload ${current}`}
          </button>
        </div>
      ) : (
        <div className="space-y-3 rounded-lg border border-emerald-200 bg-emerald-50 p-6">
          <p className="text-base font-semibold text-emerald-900">
            All documents uploaded.
          </p>
          <p className="text-sm text-emerald-800">
            We will now run automatic checks on your application. This usually
            takes under a minute.
          </p>
          <button
            type="button"
            disabled={pending || busy}
            onClick={() => startTransition(() => void runScrutinyAction({ applicationId }))}
            className="min-h-12 w-full rounded-md bg-zinc-900 px-5 py-3 text-base font-semibold text-white hover:bg-zinc-700 disabled:opacity-60"
          >
            {pending ? "Checking…" : "Check my application"}
          </button>
        </div>
      )}
    </div>
  );
}
