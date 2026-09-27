# Track B dependency notes (AGENTS.md: justify new top-level deps)

## recharts (added in B6 — officer metrics dashboard)
- **Why:** Prompt B6 explicitly pins `recharts` for the two dashboard charts
  (applications-over-day, risk distribution). ARCHITECTURE.md lists recharts as the
  sanctioned charting lib for Track B ("dashboard only"). No other charting option is
  in the pinned stack, and hand-rolled SVG charts would be more code to maintain.
- **Scope guard:** imported ONLY under `src/app/officer/dashboard/**` and only in a
  client component; never on citizen routes (keeps citizen First Load JS lean).
- **Version installed:** 3.10.1 (resolved by `npm install recharts`; major is v3).
  Uses the standard `ResponsiveContainer/BarChart/Bar/XAxis/YAxis/Tooltip/Cell` API.
- **No majors upgraded** beyond adding this one allowed dependency. Next/React/Tailwind
  remain at their pinned versions (next 14.2.35, react 18.3.1, tailwind 3.4.19).

## vitest (planned for B7 — RealApiClient unit tests)
- B7 DoD requires "unit test with mocked fetch for 2 endpoints incl. 404 path". A test
  runner is needed; vitest is a devDependency only (no runtime/bundle impact) and works
  with the pinned TS/Next setup without a bundler config. Noted here in advance per the
  "note why in your docs folder" rule.
