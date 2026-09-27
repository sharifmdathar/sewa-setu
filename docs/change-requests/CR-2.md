# CR-2 — Include decided applications in `GET /officer/queue`

- **Status:** PROPOSED (drafted by Track B; not applied — contract is FROZEN)
- **Raised by:** Track B (Person 2)
- **Affects:** `shared/contracts/openapi.yaml` → `/officer/queue` (description +
  server behaviour, Track A); officer queue status filter (Track B)

## Problem
The officer queue now offers a **status filter that includes `decided`** (unchecked
by default) so officers can review recently-closed applications. This is
schema-valid — `QueueItem.status` is the full `AppStatus` enum, which already
contains `decided`.

However the endpoint is documented as *"pending apps w/ risk"* (openapi.yaml,
`/officer/queue` → 200 description). If Track A implements that literally and
returns **only pending** applications, the `decided` filter will always come up
empty in real mode. Track B's mock already returns all statuses so the feature
demos correctly, but real-mode parity depends on Track A.

(This is the same "queue excludes decided" limitation noted in CR-3.)

## Proposed change (behavioural; NO schema change needed)
`GET /officer/queue` returns **all** applications (pending + decided), each as a
`QueueItem` with its current `status`. The UI is responsible for filtering/sorting.
Update the endpoint description from "pending apps w/ risk" to "all apps w/ status +
risk".

Alternative (if Track A prefers to keep the queue pending-only): add an optional
query param, e.g. `GET /officer/queue?include=decided`, and Track B will request it
when the `decided` filter is active.

## Impact on the other track
- **Track A:** return decided items (or honour `?include=decided`). Sorting by
  `riskScore` desc can stay server-side; status filtering stays client/UI-side.
- **Track B:** no code change required — the officer page already filters whatever
  `getQueue` returns by the selected statuses. If Track A keeps the queue
  pending-only and does not add the param, the `decided` option is simply inert in
  real mode (harmless).

## Do not action yet
Resolve during the paired integration phase (M4). Track B codes defensively against
the current pending-only assumption.
