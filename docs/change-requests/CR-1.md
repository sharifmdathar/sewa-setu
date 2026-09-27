# CR-1 — expose an application's documents over the contract

- **Status:** proposed (apply in the integration phase, paired)
- **Raised by:** Track A, prompt A7 (2026-09-27)
- **Affects:** `shared/contracts/openapi.yaml` (additive), Track B `ApiClient`

## Problem

The frozen contract has no way to read back which documents an application carries.
`Document` exists as a component, but its only appearance is as the *response* of
`POST /applications/{id}/documents`; nothing returns the list, and `Application` declares
exactly seven properties (`id, serviceId, status, applicantFields, createdAt, updatedAt,
timeline`) — none of them the documents.

Consequences for the journeys in SPEC.md:

- J3 (officer): the officer can read each check's `evidence` prose but cannot list the
  evidence — no file names, no `uploadedAt`, no `sha256`, so "compare the name printed on each
  document" has nothing to point at.
- J1/J4 (citizen): after an upload the citizen UI cannot show what was accepted, which is the
  normal confirmation for a document-requirement flow.
- Track A's C5 duplicate check is cross-application, so a "this file was also submitted by
  someone else" finding is currently unexplainable in the UI beyond the evidence string.

Track A keeps the bytes and the hashes in its JSON store, and `A7` deliberately does **not**
put them on the wire: `tests/contract.py` rejects any key a schema does not declare, so a
`documents` field on `Application` would fail our own field-for-field conformance test.

## Proposed diff

One read-only path, reusing the existing `Document` component unchanged:

```yaml
  /applications/{id}/documents:
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
                    {
                      schema:
                        {
                          type: array,
                          items: { $ref: "#/components/schemas/Document" },
                        },
                    },
                },
            },
          "404": { description: not found },
        }
```

No schema is modified, so this is additive.

## Impact on the other track

- **Track A:** one new GET route over data already stored
  (`pipeline/api/repository.py` → `record["documents"]`, shaped by the existing
  `document_view`). No pipeline change.
- **Track B:** `ApiClient` gains `listDocuments(applicationId): Promise<Document[]>`;
  `MockApiClient` needs a `documents` fixture array per application. Prism serves it for free
  from the regenerated contract. Officer report view can render an evidence panel; the citizen
  timeline can show accepted files.
- **Demo risk if deferred:** the officer UI ships with prose-only evidence. Workable for the
  5-minute script, weaker for the "every check has evidence" acceptance criterion (SPEC §8.3).

## Alternative considered and rejected

Widen `Application` with `documents: Document[]`. Rejected: `Application` is returned by both
`POST /applications` and `GET /applications/{id}`, so this changes two existing responses and
Track B's generated types, for data that is naturally a sub-resource. The additive GET costs
Track B one method instead of a type change.

## Validation (I1, pre-applied to a copy — not the frozen file)

- Applied the `get:` block above to a scratch copy of the contract; `yaml.safe_load` parses; the
  live conformance suite passes **except** `test_no_contract_path_goes_unjudged` — by design,
  because CR-1 adds a path with no test yet. That guard is exactly the obligation it creates:
  **Track A must add a documents-GET test on landing.**
- Payload checks: a `Document[]` response is accepted; a `Document` carrying `contentBase64` is
  rejected (bytes never go on the wire).
- **Insertion caveat:** the `get:` goes *inside* the existing `/applications/{id}/documents:`
  mapping, after its `post:` — a second top-level `/applications/{id}/documents:` key would be
  invalid YAML.
