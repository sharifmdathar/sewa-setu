# CR-1 — Add chart-ready series to `MetricsSummary`

- **Status:** PROPOSED (drafted by Track B during prompt B6; not applied — contract is FROZEN)
- **Raised by:** Track B (Person 2)
- **Affects:** `shared/contracts/openapi.yaml` → `components.schemas.MetricsSummary`;
  server `GET /metrics/summary` (Track A); officer dashboard (Track B, B6)

## Problem
Prompt B6 asks the officer dashboard to render **two charts** — *applications over
day* and *risk distribution* — while "consuming `getMetrics` only". The frozen
`MetricsSummary` schema exposes only scalars:

    applicationsTotal, pending, decided, avgScrutinySeconds, flagRate,
    evalPrecision?, evalRecall?, generatedAt

None of these can produce a per-day time series or a risk-band histogram. There is
no contract endpoint that yields applications **per day** at all (and `/officer/queue`
excludes decided applications, so it undercounts history).

## Interim behaviour (what B6 ships today, contract-respecting)
- Metric **cards** are built strictly from `getMetrics` (exact fit).
- **Risk-distribution** chart is derived from `getQueue` (the only endpoint that
  carries per-application `riskScore`), bucketed low <30 / medium 30–59 / high ≥60
  (SPEC §7 flag threshold).
- **Applications-over-day** chart is derived from `getQueue[].updatedAt` bucketed by
  calendar date. This is an approximation: it omits decided applications and uses
  last-update time, not creation time.

This is the reason B6 deviates from the literal "getMetrics only" wording; see the
B6 commit and handoff notes.

## Proposed change (ADDITIVE + OPTIONAL → backward compatible)
Extend `MetricsSummary` with two optional arrays. Existing consumers are unaffected;
Track A may populate them when available.

```yaml
    MetricsSummary:
      properties:
        # ... existing fields unchanged ...
        applicationsByDay:
          type: array
          items:
            type: object
            required: [date, count]
            properties:
              date: { type: string, format: date }      # ISO day, e.g. 2026-09-20
              count: { type: integer, minimum: 0 }
        riskDistribution:
          type: array
          items:
            type: object
            required: [band, count]
            properties:
              band: { type: string, enum: [low, medium, high] }   # <30 / 30–59 / ≥60
              count: { type: integer, minimum: 0 }
```

## Impact on the other track
- **Track A:** populate both arrays in `GET /metrics/summary` from the JSON store.
  If a series is unavailable, omit it (fields are optional) and the UI keeps the
  getQueue-based fallback.
- **Track B:** once applied (integration phase), B6 dashboard switches the two
  charts from the getQueue stopgap to `getMetrics` and becomes literally
  "getMetrics-only" as intended. No component-shape change needed; only the data
  source line in `officer/dashboard/page.tsx`.

## Do not action yet
Apply only during the paired integration phase (M4). Until then Track B codes
against the optional-fields shape above defensively (feature-detects presence).
