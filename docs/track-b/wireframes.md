# Track B — Wireframes (as-built, ASCII per screen)

One box per route in `apps/web/src/app`. Annotated with the component that
renders each region (see `ui-guidelines.md`). `[C]` = client island,
everything else is a Server Component; arrows are Server Action posts.

## Global shell — `app/layout.tsx`
```
┌────────────────────────────────────────────────────────────┐
│ Sewa Setu · demo          [Citizen | Officer]  ← RoleSwitcher
├────────────────────────────────────────────────────────────┤
│                                                            │
│                  (page content segment)                    │
│       loading.tsx skeleton / error.tsx / not-found slot    │
└────────────────────────────────────────────────────────────┘
```

## `/` — landing (`page.tsx`)
```
        Sewa Setu — Agentic Scrutiny & Document Verification
   Two roles, one contract.  Choose a role to begin:
   ┌───────────────┐   ┌───────────────┐
   │   Citizen →   │   │   Officer →   │   (big cards, whole=link)
   └───────────────┘   └───────────────┘
```

## `/citizen` — J1.1 services
```
  Apply for a certificate
  Choose a service to start…
  ┌──────────────────────────┐ ┌──────────────────────────┐
  │ Income Certificate       │ │ Caste Certificate        │ …
  │ Docs needed: id_proof, … │ │ Docs needed: id_proof, … │
  │ [ Apply now ]            │ │ [ Apply now ]            │
  └──────────────────────────┘ └──────────────────────────┘
  whole card = <Link> to apply; "Step 1 of 4" implied by next screen
```

## `/citizen/services/[serviceId]/apply` — J1.2 dynamic form
```
  Step 2 of 4
  Apply for {service.name}
  "Fill in your details exactly as they appear on your documents."
  ┌ ApplyForm [C] ────────────────────┐
  │ Full name        [________]       │  ← one input per
  │ Date of birth    [____] 📅        │    fieldSchema entry
  │ Monthly income   [____]           │    (lib/fields.ts)
  │ Residential addr [________]       │
  │ [ Submit application ]  (busy →)  │
  └───────────────────────────────────┘   │ form action=createApplicationAction
  ← Back to services                      ↓ redirect → /citizen/apps/[id]/upload
```

## `/citizen/apps/[id]/upload` — J1.3 documents
```
  Step 3 of 4 · Application app-1008 · [documents_uploaded]  ← StatusBadge
  ┌ UploadPanel [C] ──────────────────────────────┐
  │ Doc type [id_proof      ▾]  file [choose…]    │
  │ [ Upload document ]  (spinner while pending)  │ → uploadDocumentAction
  │ ✓ id_proof   aadhaar.txt   mock-sha-0114      │
  │ ✓ income_proof income.txt  mock-sha-0115      │
  │ ───────────────────────────────────────────── │
  │ [ ▶ Run scrutiny ]  (busy ~1.2 s)             │ → runScrutinyAction
  └───────────────────────────────────────────────┘
```

## `/citizen/apps/[id]` — J1.4 timeline + J4 feed
```
  Step 4 of 4 · Income Certificate · [scrutiny_done]
  ┌ notifications banner [C] (only on new officer/system event) ┐
  │ 📣 Officer decision: approve — notes…            [dismiss ×]│
  └──────────────────────────────────────────────────────────────┘
  StatusFeed [C] — polls /citizen/apps/[id]/feed every 30 s
  ┌ timeline <ol> (newest first) ──────────────────────┐
  │ ● 2026-09-27 12:31 officer  decision_approved      │
  │   "Officer decision: approve. Notes: Demo approve" │
  │ ● 12:29 system  scrutiny_done  risk 25, manual…    │
  │ ● 12:27 citizen documents_uploaded (income_proof)  │
  │ ● 12:25 citizen application_created                │
  └────────────────────────────────────────────────────┘
```

## `/citizen/apps` — my applications
```
  My applications
  ┌ app-1008 · Income Certificate · [scrutiny_done] · 2 m ago ┐
  ┌ app-1004 · Income Certificate · [info_requested] · …      ┐  ← rows link
  empty store → EmptyState("No open applications", [Browse])     to detail
```

## `/officer` — J3.1 queue
```
  Officer queue            filters: status=[all ▾] risk=[all ▾] (GET params)
  ┌──────────┬──────────┬───────────────┬──────┬──────────────┐
  │ App      │ Service  │ Status        │ Risk │ Updated      │
  ├──────────┼──────────┼───────────────┼──────┼──────────────┤
  │ app-1002 │ Caste    │ [info_req.]   │ ▓▓74 │ 2026-09-22   │ ← RiskMeter:
  │ app-1006 │ Income   │ [scrutiny_done]│ ▓▓68 │ 2026-09-21  │   high=red row
  │ app-1001 │ Income   │ [scrutiny_done]│ ▒25  │ 2026-09-20  │   tint
  │ app-1005 │ Caste    │ [docs_uploaded]│ 0    │ 2026-09-20  │
  └──────────┴──────────┴───────────────┴──────┴──────────────┘
  sorted riskScore desc · rows link to report · empty → EmptyState
```

## `/officer/apps/[id]` — J3.2 report + decision
```
  {Service} #app-1002 · Bikash Thapa · created …      [info_requested]
  ── two columns: report (fluid) │ decision panel (320 px) ──
  ┌ risk strip ────────────────────────────────────────────┐
  │ Risk ▓▓ 74 (high) · Rec: manual_review                 │
  │        generated 2026-09-20 10:09 · mock/mock · 4200 ms│
  └────────────────────────────────────────────────────────┘
  ┌ Checks (C1–C5) — CheckList, ALL five, always expanded ─┐
  │ ✗ C4 cross_field  [high]  [field_mismatch] Declared…   │
  │     why: "The address you filled in does not match…"   │
  │ ✗ C5 fraud        [high]  [duplicate_hash] sha… used…  │
  │ ✓ C1 identity · ✓ C2 validity · ✓ C3 completeness      │
  └────────────────────────────────────────────────────────┘
  ┌ Declared vs extracted fields (table) ──────────────────┐
  │ address │ declared "9 Hill Road…" │ doc "44 Lakeside…" │
  └────────────────────────────────────────────────────────┘
  ┌ DecisionPanel [C] (right rail, sticky) ──────────────┐
  │ (•) approve  ( ) reject  ( ) request_info              │
  │ Notes [──────────────────]  (required on reject)       │
  │ [ Record decision ] → postDecisionAction               │
  │   → redirect ?done=1 → "Decision recorded" banner      │
  └────────────────────────────────────────────────────────┘
  ▸ Raw timeline (<details>, same data as citizen sees)
  ← Back to queue
  decided/info_requested → panel disabled (already acted)
  no report yet → amber banner "Scrutiny has not been run…"
  unknown id    → notFound() → global 404 page
```

## `/officer/dashboard` — J3.3 metrics (B6)
```
  Metrics · generated 12:33:41
  ┌ Total 8 ┐ ┌ Pending 7 ┐ ┌ Decided 1 ┐ ┌ Avg scrutiny 4.4 s ┐ ┌ Flag rate 0.33 ┐
  ┌ Eval precision 0.92 · recall 0.87 (getMetrics optional fields) ┐
  ┌────────────────────────────┐ ┌────────────────────────────┐
  │ Applications by day        │ │ Risk distribution          │
  │ ▇ 09-19 ▇▇ 09-20 ▇ 09-21 … │ │ ▇▇▇ low ▇ medium ▓▓ high   │
  │ (BarChart, recharts [C])   │ │ bands: <30 / 30-59 / ≥60   │
  └────────────────────────────┘ └────────────────────────────┘
  data: getMetrics (cards) + getQueue (charts, CR-3 stopgap)
```

## BOUNDARY MAP (client islands & route handlers)
```
server (RSC + Server Actions)                 client [C]            route handler
  all pages, CheckList, RiskMeter…              StatusFeed           /citizen/apps/[id]/feed
  createApplication/upload/runScrutiny          UploadPanel          (BFF poll endpoint,
  postDecision                                  ApplyForm,            304-style diffing)
                                                DecisionPanel,
                                                banner, RoleSwitcher  charts.tsx (recharts)
```
