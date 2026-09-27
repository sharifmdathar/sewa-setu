# Workstreams & conflict-free collaboration protocol

## Ownership matrix
| Person | Branch   | Writable paths | Prompts file |
|--------|----------|----------------|--------------|
| 1      | `track-a` | `services/pipeline/**`, `eval/**`, `data/synthetic/**`, `docs/track-a/**` | agents/track-a/prompts.md |
| 2      | `track-b` | `apps/web/**`, `docs/track-b/**` | agents/track-b/prompts.md |

## Hard rules (also in AGENTS.md — agents enforce these)
1. Read anything, write ONLY your paths. Never edit root files, SPEC, ARCHITECTURE,
   README, or the contract. Violation = revert.
2. `main` accepts merges ONLY during integration phase, paired, in one session.
3. Commit messages: `track-a: <imperative summary>` / `track-b: ...`.
4. One prompt = one agent session = one commit (or a tight series), after DoD verified.
5. Need a contract/spec change? Append `docs/change-requests/CR-<n>.md`
   (problem, proposed diff, impact on other track). Do NOT edit the shared file.
6. Each track owns its own package manifest & lockfile → no shared lockfile conflicts.
7. 10-min sync daily: demo what works, flag CRs. No other coordination needed.

## Milestones
- M0 scaffold + freeze (pair, 30 min)
- M1 each track runs locally against mocks/fixtures (prompts A1–A2 / B1–B2)
- M2 core loop works within track (A3–A6 / B3–B5)
- M3 track-complete: A7–A9 (API+eval+docs), B6–B9 (dashboard, real client, demo hardening)
- M4 integration I1–I4 (pair, half day)
- M5 submission polish (pair, prompts in docs/submission/outline.md)