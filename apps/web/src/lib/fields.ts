// Safe narrowing of contract Service.fieldSchema (open `type: object` in the
// frozen contract). We only render fields we understand; unknown shapes are
// skipped, never crash. Keys are the applicantFields keys (B3 dynamic forms).

export type FieldDef = {
  label: string;
  required: boolean;
} & (
  | { type: "text" }
  | { type: "date" }
  | { type: "number" }
);

const ALIASES: Record<string, FieldDef["type"]> = {
  string: "text",
  text: "text",
  date: "date",
  number: "number",
  integer: "number",
  int: "number",
  float: "number",
  decimal: "number",
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** "aadhaarNumber" -> "Aadhaar Number" (label when the schema gives none). */
function humanizeLabel(key: string): string {
  const spaced = key
    .replace(/[_-]+/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/**
 * fieldSchema (contract: free-form object) -> ordered renderable fields.
 * Handles both shapes seen in the wild:
 *  - flat (real API):   { fieldName: "string" | "date" | "integer" | ... }
 *  - structured (mock): { fieldName: { type, label, required } }
 * Unknown types are skipped (forward-compatible), never crash.
 */
export function parseFieldSchema(schema: unknown): { name: string; def: FieldDef }[] {
  if (!isRecord(schema)) return [];
  const out: { name: string; def: FieldDef }[] = [];
  for (const [name, raw] of Object.entries(schema)) {
    // Flat shape: value is the type string.
    if (typeof raw === "string") {
      const t = ALIASES[raw.toLowerCase()];
      if (!t) continue;
      out.push({ name, def: { type: t, label: humanizeLabel(name), required: true } });
      continue;
    }
    // Structured shape: value is { type, label?, required? }.
    if (!isRecord(raw)) continue;
    const t = ALIASES[String(raw.type ?? "").toLowerCase()];
    if (!t) continue;
    out.push({
      name,
      def: {
        type: t,
        label: typeof raw.label === "string" && raw.label ? raw.label : humanizeLabel(name),
        required: raw.required === true,
      },
    });
  }
  return out;
}

const CONTROL_CLASS =
  "min-h-12 w-full rounded-md border border-zinc-300 bg-white px-3 py-3 text-base focus:border-zinc-900 focus:outline-none focus:ring-1 focus:ring-zinc-900";

/** HTML input attrs for a FieldDef (plain form POST -> server action). */
export function inputProps(name: string, def: FieldDef) {
  return {
    name,
    id: `field-${name}`,
    required: def.required,
    type: def.type === "number" ? ("number" as const) : ("text" as const),
    ...(def.type === "date" ? { type: "date" as const } : {}),
    className: CONTROL_CLASS,
    "aria-required": def.required,
  };
}

/** Collect applicantFields from a plain form POST (skips bookkeeping keys). */
export function fieldsFromFormData(
  fd: FormData,
  fields: { name: string; def: FieldDef }[],
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const { name, def } of fields) {
    const v = fd.get(name);
    if (typeof v !== "string" || v === "") continue;
    out[name] = def.type === "number" ? Number(v) : v;
  }
  return out;
}

/** Readable value for rendering declared fields (timeline, reports). */
export function formatFieldValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return v.toLocaleString("en-IN");
  return String(v);
}

// The contract types applicantFields as a bare object, so no validator can catch a wrong key
// here - the mock fixtures say "applicantName" and the real API says "fullName", and reading
// only the first rendered an em-dash on every row against the live API. CR-5 proposes a
// Service.nameField so this is declared rather than guessed; until then, take whichever the
// application actually carries. One resolver for every view, so the queue and the report
// cannot disagree about who applied.
const NAME_KEYS = ["fullName", "applicantName", "name"] as const;

export function applicantNameOf(fields: Record<string, unknown>): string | null {
  for (const key of NAME_KEYS) {
    const value = fields[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}
