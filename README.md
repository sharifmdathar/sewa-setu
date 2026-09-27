# Sewa Setu — Agentic Application Scrutiny & Document Verification (PS1)

POC for Problem Statement 1: an agentic AI pipeline that scrutinizes citizen
applications (OCR/VLM extraction → rule validation → LLM adjudication → fraud
scoring) and gives officers explainable decision support. Human-in-the-loop:
the agent recommends, the officer decides.

## Repo layout & ownership (see WORKSTREAMS.md for rules)

| Path                          | Owner    | Purpose                              |
|-------------------------------|----------|--------------------------------------|
| `shared/contracts/openapi.yaml` | FROZEN  | The only truth between tracks        |
| `services/pipeline/**`, `eval/**`, `data/synthetic/**` | Person 1 (Track A) | AI pipeline, evals, synthetic data |
| `apps/web/**`                 | Person 2 (Track B) | Citizen + officer web app, dashboard |
| `docs/track-a/**`, `docs/track-b/**` | respective owner | notes, design docs |
| `docs/change-requests/**`     | both (append-only) | proposed contract/spec changes |
| everything else at root       | FROZEN after scaffold | edit only in integration phase, paired |

## Bootstrap (pair session, once)
1. Create repo, add all scaffold files, commit: `scaffold: v1 + contract freeze`
2. `git branch track-a && git branch track-b` (both from main; main is integration-only)
3. Each person works only on their branch, only in their paths.

## Run
- Track A: `cd services/pipeline && pip install -e .[dev] && uvicorn pipeline.api.main:app --port 8000`
- Track B: `cd apps/web && npm install && npm run dev` (mock API by default; `API_MODE=real` + `API_BASE_URL` for integration)
- Mock server for Track B dev: `npx @stoplight/prism-cli mock shared/contracts/openapi.yaml --port 8000`

## Integration (pair session, see agents/integration/prompts.md)
Merge track branches into main only during integration phase.