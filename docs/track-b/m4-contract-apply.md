# M4 — Contract apply runbook (CR-1 / CR-2 / CR-3)

**Purpose:** turn the paired M4 session from "draft" into "apply + test". Each change is
already validated (see the `Validation`/`Validated diff` sections in the CR files). This is
the ordered, copy-paste procedure.

**Safety**
- `shared/contracts/openapi.yaml` is FROZEN until this session — do not edit it outside the
  paired session. Take a checkpoint first: `git tag m4-pre-contract` (rollback = `git reset
  --hard m4-pre-contract`).
- Apply **one CR at a time**, validate + run the gates, commit, then the next. Do not batch.
- Line numbers below are from the frozen v1.0.0 file; **re-locate by the surrounding text**,
  not the number, in case the file shifted.

**Prereqs (both tracks)**
- Track A venv active; server up: `uvicorn pipeline.api.main:app --port 8000` (log `/tmp/sewa-api.log`).
- Track B deps installed: `cd apps/web && npm install`.
- Seed data for real-mode checks: `python -m pipeline.scripts.seed_demo` (idempotent;
  add `--limit 26` to show the duplicate-hash pair APP-0009/APP-0026).

---

## Order of application

CR-2 (1 line, unblocks the queue/pending divergence) → CR-3 (MetricsSummary series) →
CR-1 (new GET path + Track A route + test). Each section: contract edit → Track A landing →
Track B landing → verify.

---

## CR-2 — queue returns all statuses; align `pending`

**Contract edit** — `/officer/queue` → 200 response, one line:
```diff
-              description: pending apps w/ risk,
+              description: all apps w/ status + risk,
```
No schema change (`QueueItem.status` is already the full `AppStatus` enum incl. `decided`).

**Track A landing** (`services/pipeline/pipeline/api/repository.py`):
- In `queue()`: drop the `status != QUEUE_STATUS` filter; keep the risk-desc sort; remove the
  now-unused `QUEUE_STATUS = "scrutiny_done"` constant.
- Make `metrics.pending` and `queue` share **one** status set so the `pending: 21` vs
  `queue: 20` divergence cannot return. Reuse `OPEN_STATUSES` as the single definition.

**Track B landing:** none — the officer page already filters `getQueue` client-side by the
status checkboxes; it becomes correct the moment the queue returns all statuses.

**Verify**
- `python -m pytest -q services/pipeline/tests` (update any queue-shape assertions).
- `curl -s :8000/officer/queue | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d),sorted({x['status'] for x in d}))"`
  → expect statuses beyond `scrutiny_done` once non-scrutiny apps exist.
- `curl -s :8000/metrics/summary` → `pending` should now equal the queue's open count.

---

## CR-3 — MetricsSummary chart series (additive, optional)

**Contract edit** — inside `MetricsSummary.properties`, add two keys. **Leave `required`
at its current 6** (both arrays optional → backward compatible):
```yaml
            applicationsByDay:
              { type: array, items: { type: object, required: [date, count],
                properties: { date: { type: string, format: date },
                              count: { type: integer, minimum: 0 } } } }
            riskDistribution:
              { type: array, items: { type: object, required: [band, count],
                properties: { band: { type: string, enum: [low, medium, high] },
                              count: { type: integer, minimum: 0 } } } }
```

**Track A landing** (`repository.metrics()`): populate both from the store —
`applicationsByDay` bucketed by `createdAt` day (ISO `YYYY-MM-DD`); `riskDistribution`
counted into `<30 / 30–59 / >=60` bands (SPEC §7 flag threshold). **Omit** a series when there
is no data (the UI feature-detects). Note: `format: date` validation already lives in
`tests/contract.py`.

**Track B landing** (`apps/web/src/app/officer/dashboard/page.tsx`): switch the two charts from
the `getQueue` stopgap to `metrics.applicationsByDay` / `metrics.riskDistribution` when present,
else fall back to the current `appsByDay(queue)` / `riskDistribution(queue)`. Add the two
optional fields to `MetricsSummary` in `src/lib/api/types.ts` (matching the contract exactly).
Then the dashboard is literally "getMetrics-only" as B6 intended.

**Verify**
- `curl -s :8000/metrics/summary | python3 -m json.tool` → `applicationsByDay` + `riskDistribution` present and well-shaped.
- Track B: `cd apps/web && npm run build && npm test` → dashboard renders series (and still
  renders when they're absent — test the fallback).

---

## CR-1 — GET /applications/{id}/documents (new read path)

**Contract edit** — add a `get:` **inside the existing `/applications/{id}/documents:`
mapping, after its `post:`** (a second top-level path key would be invalid YAML):
```yaml
    get:
      parameters:
        [{ name: id, in: path, required: true, schema: { type: string } }]
      responses:
        {
          "200":
            {
              description: uploaded documents,
              content:
                {
                  application/json:
                    { schema: { type: array, items: { $ref: "#/components/schemas/Document" } } },
                },
            },
          "404": { description: not found },
        }
```

**Track A landing** (`pipeline/api`): one route returning
`[document_view(d) for d in record["documents"]]`, 404 on unknown id. **Plus a test** —
`test_no_contract_path_goes_unjudged` deliberately fails until it exists (that guard is the
obligation, not a bug).

**Track B landing (optional, not required to pass M4):** add
`listDocuments(applicationId): Promise<Document[]>` to `ApiClient` + `RealApiClient` +
`MockApiClient` (a `documents` fixture per app), and render an evidence panel on the officer
report / accepted-files list on the citizen timeline. Defer if time-boxed — the demo works
without it (prose-only evidence).

**Verify**
- `curl -s :8000/applications/APP-0001/documents` → array of `Document` (no `contentBase64`).
- `python -m pytest -q services/pipeline/tests/test_api_live_contract.py` → all pass incl. the
  coverage guard.

---

## Combined gate (after all three applied)

- Track A: `ruff check .` + `python -m pytest -q` (services/pipeline) + `ruff check .` +
  `pytest -q` (eval) + `python -m eval.gate` → PASS.
- Track B: `cd apps/web && npm run lint && npx tsc --noEmit && npm test && npm run build`.
- Live: `python -m pipeline.scripts.seed_demo`, boot Track B in real mode
  (`API_MODE=real API_BASE_URL=http://localhost:8000`), run the **B8 checklist**
  (`apps/web/docs/track-b/demo-checklist.md`) end-to-end against the real API.
- Commit the contract change: `integration: apply CR-1/2/3` (paired, both authors).

## Then I4
Run `docs/demo/script.md` twice, record the fallback video, tag `v1.0-poc`.
