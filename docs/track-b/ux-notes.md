# Track B — UX notes: journey rationale vs SPEC.md §4

Companion to `ui-guidelines.md` (component/visual rules). This file records
*why* each journey screen is shaped the way it is, tied to SPEC §4/§5.

## Design stance
Two audiences, one product: a citizen in a government office (low trust,
one-task-at-a-time) and an officer under queue pressure (high volume,
accountability). The UI deliberately sits at opposite ends of the density
spectrum per role — see ui-guidelines §2 — because a shared "enterprise"
look would fail both.

## J1 — Citizen: browse → apply → upload → timeline
- **Whole card is the action** on the service list: fewer decision points,
  nothing to mis-tap; "Apply now" is painted on the card, not a second CTA.
- **Form built from `Service.fieldSchema` at render time** (not hardcoded):
  the contract owns the fields, so Track A adding a service needs no UI
  change. `lib/fields.ts` maps schema types → native inputs.
- **4-step progress header** ("Step n of 4") on every citizen screen —
  SPEC's baseline complaint is confusion; always knowing how much is left
  is the core reassurance.
- **Uploads + Run scrutiny are explicit buttons with visible busy state**:
  J2 (the pipeline run) is triggered through the citizen surface in demo
  mode; making it a named action keeps the magic accountable.
- Server Actions + plain `<form action>`: every citizen step works without
  JS (progressive enhancement); client islands only add optimistic states.

## J2 — System: scrutiny
Not a screen, but it *is* one on the timeline: `scrutiny_done` renders with
risk score + recommendation in citizen wording ("We finished the automatic
check"), never raw JSON. Evidence strings are shown verbatim in the
timeline message — the citizen is the auditor of record for their own file.

## J3 — Officer: queue → report → decision
- **Queue sorted riskScore desc, high band red-tinted**: the pipeline's
  output is a *triage order*; the UI's job is to make position 1 obvious.
  Filters are GET query-params (`?status=&risk=`) — linkable, no-JS.
- **Report = all five checks, always**: pass, warn, or fail, every check
  shows evidence + plain-language explanation (SPEC §5 "every check MUST
  emit"). Nothing is collapsible-away; a `warn` is rendered as loudly as a
  `fail` because recall matters more than a tidy screen.
- **Decision panel mirrors the contract enum** exactly
  (approve / reject / request_info) + mandatory notes → `postDecision`.
  Recommendation is shown as advice, never pre-filled as the decision:
  the officer is accountable, the model is not.
- **Declared vs extracted fields table** sits under the checks — C4
  failures are verifiable side-by-side without re-reading the evidence.

## J4 — Citizen: decision & info-request
- Status feed polls `getApplication` every 30 s while the page is open
  (B5) — no push/email in scope (SPEC §3 out); a dismissible banner on new
  officer/system events is the "lightweight notification".
- Tab re-focus triggers an immediate poll (visibilitychange): in a demo the
  officer→citizen handoff should take seconds, not up to 30.
- `info_requested` renders in the same timeline with the officer's note —
  one surface for all outcomes; no separate "inbox".

## Empty / error / loading doctrine (B8)
- Empty states always offer one next action (ui-guidelines §1.4).
- Loading is a segment-level skeleton — structure appears before data.
- Errors are ErrorState + retry, never a stack trace; unknown ids land on
  the branded 404. Mock vs real failures read the same way by design
  (B7 maps HTTP errors into the same shape).

## Known compromises
- Charts bucket `getQueue.updatedAt` until CR-3 (Metrics series fields).
- Auth is the role switcher (SPEC §3 explicitly out of scope).
- Poll-based feed would become SSE/event-stream at productionization.
