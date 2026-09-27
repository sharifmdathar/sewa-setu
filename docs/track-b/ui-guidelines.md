# UI guidelines — Sewa Setu POC (Track B)

Written before any B2 code, per prompt B2. Two audiences, two design poles:
**citizen = simple**, **officer = dense**. Everything here maps to SPEC.md §4
journeys (J1/J3/J4) and §5 explainability (every check shows evidence + explanation).

## 1. Citizen surfaces (J1, J4) — simple pole

### 1.1 One primary action per screen
- Services list → primary action: *pick a service* (whole card is the button).
- Application form → primary action: *submit application*. Everything else secondary.
- Upload screen → primary action: *upload the next required document*; "done" only
  enabled when all `requiredDocTypes` are uploaded.
- Timeline screen → primary action: *nothing* (read-only status). If info was
  requested, the single primary action is *upload the requested document*.
- No modal-on-load, no competing CTAs, no more than one filled (high-contrast)
  button on screen.

### 1.2 Large touch targets
- Minimum hit area 48×48 px (`min-h-12 min-w-12`), spacing ≥ 12 px between targets.
- Inputs full-width with `py-3`+; checkboxes/radios rendered as tappable label rows.
- Bottom of screen is prime territory for the primary action on mobile (thumb zone);
  secondary actions go above it.

### 1.3 Plain language
- Button copy = verb + noun the citizen already used: "Apply for Income
  Certificate", not "Create application".
- Status copy explains what happens next: "Your documents are being checked.
  This usually takes under a minute." — never raw enums on citizen screens.
  Enum → copy map lives in `StatusBadge` (single source).
- Errors say what to fix, not what broke internally: "Please upload a clearer
  photo of your ID", never "OCR confidence below threshold".
- Jargon (risk score, scrutiny, adjudication) does not appear on citizen screens;
  the citizen sees *status* and *what to do*, the officer sees the report.

### 1.4 Flow discipline
- ≤ 4 steps to finish J1: service → form → upload → done. Progress indicator
  ("Step 2 of 4") on every step.
- Back is always safe (state kept); no confirmation dialogs on a single-screen action.
- Empty states (B8) show one next action, never a shrug.

## 2. Officer surfaces (J3) — density pole

- Queue = table, sortable/filterable, default sort riskScore desc; row height
  compact (36 px), monospace IDs, inline `RiskMeter` bars and `StatusBadge`s.
- Report view shows **all five checks at a glance** (status + severity visible
  without expanding); evidence + explanation expand in place — never hidden
  behind navigation (SPEC §8.3).
- Decision panel is sticky-right on desktop: approve / reject / request_info +
  notes; keyboard reachable; notes required for reject.
- Density over delight here: smaller type (12–13 px) is acceptable, whitespace
  tight, colour reserved for status semantics only.
- Counts/metrics up top (B6 dashboard) so the officer triages by risk, not scroll.

## 3. Shared rules (both poles)

- **Roles**: role switcher (citizen/officer) is a POC stand-in for auth
  (SPEC §3 OUT). Default landing = last chosen role (persisted); no real login.
- **Status colour semantics** (identical everywhere, defined once in components):
  - green = pass / approve-track (pass, submitted→decided happy path)
  - amber = warn / in-flight (warn, scrutiny_pending, info_requested)
  - red = fail / reject (fail, high risk)
  - blue = info / neutral (info, decided, documents_uploaded)
  - Colour is never the only signal — every badge pairs colour with text.
- **Risk bands**: low < 30 (green), medium 30–59 (amber), high ≥ 60 (red) —
  60 = the eval flag threshold (SPEC §7), so UI and eval agree.
- **Data path**: components render data typed by `src/lib/api/types.ts`; fetched
  only via `ApiClient` in server components (AGENTS.md). No enum strings retyped.
- **Every LLM/scrutiny artifact on screen** carries its explanation string; if a
  field is missing, show `ErrorState`, never a blank.
- **Loading**: skeletons shaped like the final content (no spinners on full screen).
- **Accessibility**: semantic list/table, `aria-live="polite"` on status updates,
  visible focus rings, contrast ≥ 4.5:1 for body text, `details/summary` for
  expandables (works without JS).
- Files < ~300 lines (AGENTS.md); components are presentational — pages own data.

## 4. Component inventory (B2 deliverables)

| Component      | Pole     | Contract type it renders                  |
|----------------|----------|-------------------------------------------|
| `StatusBadge`  | shared   | `AppStatus`                               |
| `CheckList`    | officer  | `ScrutinyCheck[]` (status, severity, evidence, explanation) |
| `RiskMeter`    | officer  | `riskScore` 0–100 (bands per §3)          |
| `EmptyState`   | shared   | — (generic, one action slot)              |
| `ErrorState`   | shared   | — (ErrorState-friendly error mapping, B7) |
| `RoleSwitcher` | shell    | — (client component, localStorage)        |

Demo/gallery: `/dev/components` renders every component in every variant
(storybook-less, server-rendered from real fixture-shaped data).
