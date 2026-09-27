# apps/web — Sewa Setu UI (Track B)

Next.js 14 App Router front for the agentic scrutiny POC: citizen journey
(`/citizen`) and officer console (`/officer`, `/officer/dashboard`), built
strictly against `shared/contracts/openapi.yaml`. Runs fully standalone on
an in-app mock, or against the real Track A pipeline API.

## Requirements
- Node 18.17+ (developed on 26.x; anything ≥ 18.17 works).
- npm. This repo pins the stack — do not swap to bun/pnpm or upgrade
  Next/React majors without a change request.

## Quick start (mock mode — default, nothing else running)
```bash
cd apps/web
npm install          # if this env has NODE_ENV=production exported, run:
                     #   NODE_ENV=development npm install
npm run dev          # → http://localhost:3000
```
The mock is an in-memory store seeded from `src/lib/api/fixtures.ts`
(dataset-v1 shapes: 3 clean, 2 anomalous, 1 decided, 1 info_requested).
It lives in the dev-server process: **restart the server to reload the
seed**; in-flight applications are lost on restart.

Demo time: follow `docs/track-b/demo-checklist.md` — cold pass < 5 min.

## Real mode (Track A pipeline up)
```bash
cp .env.example .env.local
# .env.local:
#   API_MODE=real
#   API_BASE_URL=http://localhost:8000   # uvicorn app:app --port 8000
npm run dev
```
`API_MODE=real` swaps in `RealApiClient` (same `ApiClient` interface,
`src/lib/api/real.ts`): 10 s timeout per call, typed `ApiError` → the same
ErrorState UI; `getScrutiny` 404 renders "not run yet", not an error. No
other behaviour changes; server actions and routes are mode-agnostic.

## Commands
| Command | What |
|---|---|
| `npm run dev` | dev server on :3000 |
| `npm run lint` | eslint (next/core-web-vitals) — gate before commit |
| `npm run build` | production build + type-check — gate before commit |
| `npm start` | serve the production build |
| `npm test` | vitest unit tests (`src/lib/api/*.test.ts`, mocked fetch) |

## Layout map
```
src/app/            routes (page per screen) + loading/error/not-found boundaries
  citizen/**        J1 apply → upload → timeline, J4 status feed (BFF /feed route)
  officer/**        J3 queue → report → decision; B6 metrics dashboard
src/components/     StatusBadge, RiskMeter, CheckList, Empty/Error/Skeleton, RoleSwitcher
src/lib/api/        contract types, ApiClient seam, mock + real clients
src/lib/            fields.ts (schema→form), feed.ts (status-diff helpers)
docs/track-b/       demo-checklist.md (this app's docs live in the monorepo docs too)
```

## Troubleshooting
- **`/citizen` or `/officer` 404s on a long-running dev server** → a
  `npm run build` overwrote the shared `.next`; restart:
  `rm -rf .next && npm run dev`. Never run build while dev is live.
- **Edits to `fixtures.ts` don't show** → the store is cached on
  `globalThis`; restart the dev server.
- **`npm install` skips devDependencies** → `NODE_ENV=production` is
  exported in this shell; prefix with `NODE_ENV=development`.
- **Mock feels too fast to see loading states** → latency lives in
  `src/lib/api/mock.ts` (`LATENCY_MIN_MS`, `SCRUTINY_LATENCY_MS`).

## Deeper docs
`docs/track-b/ui-guidelines.md` (component rules), `ux-notes.md`
(journey rationale), `wireframes.md` (as-built screens),
`docs/change-requests/CR-1.md` (metrics chart data, pending integration).
