# Architecture

## Diagram
```mermaid
flowchart LR
  C[Citizen UI] -->|contract API| B[Web app / BFF route handlers]
  B -->|HTTP JSON| A[Pipeline API FastAPI]
  A --> EX[Extraction: TemplateExtractor | LLMExtractor VLM]
  EX --> RE[Rules engine YAML C1-C5]
  RE --> ADJ[LLM adjudicator: warn/ambiguous → explanation]
  RE --> FR[Fraud scorer: dup hash, tamper patterns]
  ADJ & FR --> REP[ScrutinyReport + riskScore + recommendation]
  REP --> ST[(JSON file store)]
  EV[Eval runner] --> A
  GEN[Synthetic generator] --> DS[(dataset-v1 + ground truth)] --> EV
  Contract-first development
shared/contracts/openapi.yaml v1 is FROZEN. Track B codes against Prism mock
(or its in-app MockApiClient). Track A implements the spec exactly.
Need a change? Write docs/change-requests/CR-<n>.md; applied only in integration phase, paired.
Stacks (pinned — agents must not substitute)
Track A: Python 3.11, FastAPI, pydantic v2, httpx, openai SDK (any OpenAI-compatible
endpoint via LLM_BASE_URL), PyYAML, pytest, ruff. No orchestration frameworks.
Track B: TypeScript, Next.js (app router), Tailwind, recharts (dashboard only).
ApiClient interface with MockApiClient (fixtures) and RealApiClient (fetch).
Persistence & config
Track A: JSON file store under services/pipeline/var/ (gitignored).
Env per track via .env.example in each track dir. Secrets never committed.
LLM calls: timeout 30 s, 2 retries, record modelMeta (model, latency, versions).
Explainability & safety invariants
No check without evidence + explanation. Agent never auto-decides: recommendation
only; officer decision required (human-in-the-loop).
Synthetic data only; design registry integrations as adapters behind interfaces
(roadmap, not POC).
Integration plan
I1 conformance (RealApiClient ↔ Track A API), I2 seed store from dataset-v1,
I3 eval run + metrics wiring, I4 demo rehearsal/recording. (agents/integration/prompts.md)


---

## `WORKSTREAMS.md`

```markdown
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