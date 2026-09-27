# Architecture

## Diagram

    flowchart LR
      C[Citizen UI] -->|contract API| B[Web app / BFF route handlers]
      B -->|HTTP JSON| A[Pipeline API FastAPI]
      A --> EX[Extraction: TemplateExtractor | LLMExtractor VLM]
      EX --> RE[Rules engine YAML C1-C5]
      RE --> ADJ[LLM adjudicator: warn/ambiguous -> explanation]
      RE --> FR[Fraud scorer: dup hash, tamper patterns]
      ADJ & FR --> REP[ScrutinyReport + riskScore + recommendation]
      REP --> ST[(JSON file store)]
      EV[Eval runner] --> A
      GEN[Synthetic generator] --> DS[(dataset-v1 + ground truth)] --> EV

(Render with any Mermaid viewer; arrows use `->` above to avoid fence issues —
convert to `-->` if your renderer needs it.)

## Contract-first development
- `shared/contracts/openapi.yaml` v1 is FROZEN. Track B codes against Prism mock
  (or its in-app MockApiClient). Track A implements the spec exactly.
- Need a change? Write `docs/change-requests/CR-<n>.md`; applied only in integration phase, paired.

## Stacks (pinned — agents must not substitute)
- Track A: Python 3.11, FastAPI, pydantic v2, httpx, openai SDK (any OpenAI-compatible
  endpoint via `LLM_BASE_URL`), PyYAML, pytest, ruff. No orchestration frameworks.
- Track B: TypeScript, Next.js (app router), Tailwind, recharts (dashboard only).
  `ApiClient` interface with `MockApiClient` (fixtures) and `RealApiClient` (fetch).

## Persistence & config
- Track A: JSON file store under `services/pipeline/var/` (gitignored).
- Env per track via `.env.example` in each track dir. Secrets never committed.
- LLM calls: timeout 30 s, 2 retries, record `modelMeta` (model, latency, versions).

## Explainability & safety invariants
- No check without evidence + explanation. Agent never auto-decides: recommendation
  only; officer decision required (human-in-the-loop).
- Synthetic data only; design registry integrations as adapters behind interfaces
  (roadmap, not POC).

## Integration plan
I1 conformance (RealApiClient vs Track A API), I2 seed store from dataset-v1,
I3 eval run + metrics wiring, I4 demo rehearsal/recording. (agents/integration/prompts.md)