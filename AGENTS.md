# Agent operating rules (applies to EVERY session in this repo)

You are an agentic coder in a two-track, contract-first monorepo.
Before doing anything: read README.md, WORKSTREAMS.md, SPEC.md, ARCHITECTURE.md,
and shared/contracts/openapi.yaml. Then read your track's prompt file and execute
ONLY the prompt block pasted by the human.

## Ownership & boundaries
- The human tells you which track you are in (track-a or track-b).
- WRITE only inside that track's paths (WORKSTREAMS.md matrix). Creating files
  elsewhere, or editing root/shared/spec/contract files, is FORBIDDEN.
- If the task as pasted seems to require out-of-scope writes: STOP, tell the human,
  and draft `docs/change-requests/CR-<n>.md` instead (this path is append-only for both tracks).

## Quality gates before every commit
- Track A: `ruff check .`, `pytest -q` green inside services/pipeline & eval.
- Track B: `npm run lint`, `npm run build` green inside apps/web.
- No new top-level dependencies without noting why in your track's docs folder.
- No secrets, no real PII, no `.env` commits. Keep files < ~300 lines; split otherwise.
- Implement against the contract schemas exactly (field names, enums, statuses).

## Style
- Python: type hints everywhere, pydantic models for I/O, plain functions over classes
  unless stateful. TS: strict mode, server components default, `ApiClient` interface only
  (never fetch directly in components).
- Every LLM call: timeout, retries, and modelMeta recording.
- Every scrutiny check: evidence + explanation string, always.

## Commit
Message prefix `track-a:` / `track-b:`. Commit only after gates pass.
Summarize in 1 line what changed + 1 line DoD evidence (test/command output).