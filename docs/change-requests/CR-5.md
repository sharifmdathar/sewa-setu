# CR-5 — name the applicant in the queue, and stop leaving `applicantFields` uncheckable

- **Status:** proposed (apply in the integration phase, paired). The contract is Track B's to edit
  under M4 option A; Track A is raising it, not applying it.
- **Raised by:** Track A, overnight session (2026-09-28)
- **Affects:** `shared/contracts/openapi.yaml` (additive: one optional property on `QueueItem`, one
  on `Service`), Track B `ApiClient` consumers, Track A `api/readmodel.py`

## Problem

Running the officer queue against the real API surfaced a divergence that both conformance suites
passed: **the Applicant column renders `—` on every row.** The UI reads
`applicantFields["applicantName"]`; the API sends `fullName`, which is the key
`pipeline/api/catalog.py` declares for all three services. The mock fixtures declare
`applicantName`, so the screen is correct in mock mode and empty in real mode.

Neither track is careless here, and that is the interesting part. `applicantFields` is declared as
a bare object:

```yaml
applicantFields: { type: object }
```

There is no key name inside it for a validator to check, so `tests/contract.py` — which otherwise
judges responses field-for-field against the schema — cannot see the mismatch in either direction.
The two tracks each guessed a different key and both passed their own gates. The contract held
everywhere it spoke and was silent exactly where it mattered.

There is a second cost. `QueueItem` carries `applicationId, serviceId, status, riskScore, updatedAt`
and **no name at all**, so to render one column the officer page issues one `GET /applications/{id}`
per queue item — 26 sequential round trips to draw a table that already knows 26 ids. That is an
N+1 built by necessity, not by mistake, and it is the fragile part of the screen: a single failed
lookup is swallowed by `catch { /* skip */ }` and the application disappears from the officer's
queue with no error on screen.

## Proposed change (ADDITIVE + OPTIONAL → backward compatible)

```yaml
QueueItem:
  type: object
  required: [applicationId, serviceId, status, riskScore, updatedAt]
  properties:
    applicationId: { type: string }
    serviceId: { type: string }
    status: { $ref: "#/components/schemas/AppStatus" }
    riskScore: { type: integer }
    updatedAt: { type: string, format: date-time }
    applicantName:
      type: string
      description: >-
        The applicant's name as declared on the application, so a queue can be read without
        fetching every application. Optional: an application with no name field yields none.

Service:
  type: object
  required: [id, name, requiredDocTypes]
  properties:
    id: { type: string }
    name: { type: string }
    requiredDocTypes: { type: array, items: { type: string } }
    fieldSchema: { type: object }
    nameField:
      type: string
      description: >-
        Which key of applicantFields holds the person's name (today "fullName" for all three
        services). Clients render a title from this instead of guessing a key.
```

Both are optional properties on existing schemas: every current response stays valid, and
`tests/contract.py` (which rejects *undeclared* keys, not absent optional ones) keeps passing on
both sides before either track changes anything.

**Track A's side is small.** `api/readmodel.py` already loads the record to build each queue item,
so `applicantName` is one lookup from `applicantFields[catalog.name_field]` — no extra I/O, and the
N+1 in the UI becomes unnecessary rather than merely faster. `catalog.py` gains one constant per
service.

**Track B's side is the fix that matters for the demo:** read `nameField` from `/services` (or
accept both keys) instead of hardcoding `applicantName`, and drop the per-row `getApplication` loop
in favour of the queue's own `applicantName`.

## Impact on the other track

- **Track B:** `types.ts` gains two optional fields; the officer queue loses 26 sequential fetches
  per render and gains a name column that works in real mode. The `catch { /* skip */ }` should
  become an error state regardless — a queue that silently omits applications is worse than one
  that shows a failed row, because an officer cannot tell the two apart.
- **Track A:** `readmodel.queue()` populates `applicantName`; `catalog.py` declares `nameField`.
  Both are covered by the existing conformance suite once the contract carries the keys.

## Alternatives considered and rejected

- **Just fix the key in the UI.** Correct for today and worth doing, but it leaves the next client
  free to guess a third key. The bug was possible because the contract is silent, and silence is
  the thing to fix.
- **Type `applicantFields` as a strict schema per service.** The honest long-term fix, but it is a
  breaking change to a frozen contract and far more than this defect needs. `nameField` captures
  the one key every client actually needs to know.
- **Let the queue return full `Application` objects.** Solves the N+1 by over-fetching every
  applicant field into a list screen, which is the opposite of what a queue should send.

## Validation (merged into a copy — the frozen file was not touched)

Each proposed schema was diffed against the real component in `openapi.yaml`:

```
QueueItem: required unchanged=True  added=['applicantName']  removed=none  mutated=none  added-optional=True
Service:   required unchanged=True  added=['nameField']      removed=none  mutated=none  added-optional=True
VERDICT: purely additive, nothing breaks
```

The **first draft of this CR failed that check**, and it is worth recording how, because the same
mistake is easy to make when retyping a schema by hand:

- `status` was written as `{ type: string }` where the contract has
  `{ $ref: "#/components/schemas/AppStatus" }` — a silent widening of an existing field.
- `Service.required` included `fieldSchema`, which the contract does not require — that alone
  would have made every current `/services` response invalid.

Both were caught by diffing rather than reading. Reproduce with:

```bash
python - <<'PY'
import re, yaml, json
from pathlib import Path
text = Path("docs/change-requests/CR-5.md").read_text(encoding="utf-8")
blocks = [b for b in re.findall(r"```yaml\n(.*?)```", text, re.S) if "applicantFields: {" not in b]
proposed = {}
for b in blocks:
    proposed.update(yaml.safe_load(b))
schemas = yaml.safe_load(Path("shared/contracts/openapi.yaml").read_text(encoding="utf-8"))["components"]["schemas"]
norm = lambda x: json.loads(json.dumps(x, sort_keys=True, default=str))
for name, new in sorted(proposed.items()):
    old = schemas[name]
    added = set(new["properties"]) - set(old["properties"])
    mutated = [p for p in set(old["properties"]) & set(new["properties"])
               if norm(old["properties"][p]) != norm(new["properties"][p])]
    print(name,
          "required-unchanged:", sorted(old.get("required") or []) == sorted(new.get("required") or []),
          "| added:", sorted(added),
          "| removed:", sorted(set(old["properties"]) - set(new["properties"])) or "none",
          "| mutated:", mutated or "none")
PY
```

## Scope note

The demo does not need CR-5. The one-line key fix does. CR-5 is why the key was guessable at all,
and it belongs in the integration phase with the other three.
