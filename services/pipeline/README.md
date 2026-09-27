# Track A runbook — services/pipeline

Everything here is runnable from a fresh shell on a fresh clone. Each block is the command, then
what a correct run looks like.

## What this is

The scrutiny pipeline behind the frozen contract in `shared/contracts/openapi.yaml`:
document intake → extraction → rules C1–C5 → LLM/deterministic adjudication → fraud scoring →
`ScrutinyReport`, served by FastAPI over a JSON file store. No database, no queues, no
orchestration framework.

## 0. Prerequisites

- Python 3.11+ (this repo's venv is 3.12). [`uv`](https://docs.astral.sh/uv/) is used here but a
  plain `python3.12 -m venv` works the same.
- No API key is needed: with `LLM_API_KEY` unset the pipeline uses the template extractor and the
  deterministic adjudicator. Setting it switches both to the model path (see §7).
- Everything below assumes you are at the **repository root**.

## 1. Create the environment

```bash
uv venv --seed --python 3.12 .venv      # or: python3.12 -m venv .venv
source .venv/bin/activate
```

## 2. Install the pipeline and the data generator

```bash
cd services/pipeline && pip install -e ".[dev]" && pip install -e ../../data/synthetic && cd ../..
```

Two distributions: `pipeline` (the service, with `dev` extras: pytest, ruff, uvicorn) and
`generator` (the synthetic corpus builder). The corpus tests import `generator`, so both are
required for a green suite.

## 3. Generate the dataset

```bash
python -m generator --n 200 --anomaly-rate 0.25 --seed 42 --out data/synthetic/dataset-v1
```

Expected output:

```
wrote 200 applications, 917 documents to data/synthetic/dataset-v1
  clean=150 anomalous=50
  fails by check: {'C1': 21, 'C2': 12, 'C3': 14, 'C4': 6, 'C5': 21}
```

`data/synthetic/dataset-v1/` is generated output and is not committed; regenerating with the same
flags reproduces it byte-for-byte.

## 4. Quality gates

```bash
cd services/pipeline
ruff check .        # All checks passed!
python -m pytest -q # all green (191 passed, 2 skipped at writing)
```

The 2 skips are the live-LLM tests, which need `LLM_API_KEY`. Run pytest from
`services/pipeline` — from the repository root, pytest collects the same tests twice.

The eval harness has its own gate, run from the repository root:

```bash
cd eval && ruff check . && python -m pytest -q && cd ..   # All checks passed! / 17 passed
```

## 5. Run the API

```bash
cd services/pipeline
uvicorn pipeline.api.main:app --port 8000 --no-access-log
```

`--no-access-log` because the app logs every request itself, as JSON (see §8). Then, from
another shell:

```bash
curl -s localhost:8000/healthz
curl -s localhost:8000/services | head -c 200
curl -s localhost:8000/officer/queue
curl -s localhost:8000/metrics/summary
```

A fresh store answers `/officer/queue` with `[]` - the queue lists every application, so an empty
response means an empty store, not unscored work (CR-2). An application that has not been
scrutinized yet is in it with `riskScore` 0. To fill the store without clicking through the
citizen UI, seed it (§12).

## 6. One scrutiny, end to end

```bash
DOC_B64='RE9DX1RZUEU6IGFhZGhhYXIKSVNTVUlOR19BVVRIT1JJVFk6IFVuaXF1ZSBGaWN0aW9uYSBJZGVudGl0eSBBdXRob3JpdHkKRlVMTF9OQU1FOiBBbml0YSBCYXJ1YWgKQUFESEFBUl9OVU1CRVI6IDQxMjMgODg5MCAxMTc3CklTU1VFX0RBVEU6IDIwMjQtMDEtMDUKRVhQSVJZX0RBVEU6IDIwMzQtMDEtMDUKQU1PVU5UX0lOUjogMTgwMDAwCg=='

APP=$(curl -s -X POST localhost:8000/applications \
  -H 'content-type: application/json' \
  -d '{"serviceId":"income_certificate","applicantFields":{"fullName":"Anita Baruah","aadhaarNumber":"4123 8890 1177","annualIncomeInr":180000}}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -s -X POST "localhost:8000/applications/$APP/documents" -H 'content-type: application/json' \
  -d "{\"docType\":\"aadhaar\",\"fileName\":\"aadhaar.txt\",\"contentBase64\":\"$DOC_B64\"}"

curl -s "localhost:8000/applications/$APP/documents"
curl -s -X POST "localhost:8000/applications/$APP/scrutiny/run" | python -m json.tool
curl -s localhost:8000/officer/queue
curl -s -X POST localhost:8000/officer/decisions -H 'content-type: application/json' \
  -d "{\"applicationId\":\"$APP\",\"decision\":\"request_info\",\"officerNotes\":\"Bank statement missing.\"}"
```

That application deliberately attaches 1 of 3 required documents, so the report shows
`"C3": "fail"` with the missing types named in `evidence`, and `riskScore` 27 → `approve`
(under the `requestInfoMinScore` 30 band). The full happy path, the officer queue ordering and
every error path are covered by `tests/test_api_journey.py` and `tests/test_api_errors.py`.

## 7. Optional: the model path

The service reads its configuration from the **process environment** — there is no dotenv
loader, so `export` these (or `set -a; . services/pipeline/.env; set +a` if you keep them in a
file; `.env` is gitignored and never committed):

```bash
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_API_KEY=sk-...
export LLM_MODEL=gpt-4o-mini
```

With a key set, `default_extractor()` becomes the VLM extractor and `default_adjudicator()` the
LLM adjudicator (30 s timeout, 2 retries, `modelMeta` recorded per call). Without one, nothing
breaks: extraction is the deterministic template parser and ambiguous checks keep the rule
verdict with a plain-language rewrite. The two skipped tests are exactly this branch.

Three more knobs matter once you point this at a real endpoint (see
`docs/track-a/live-model-leg.md` for why each exists):

```bash
export LLM_CACHE=1                        # answers are cached under var/llm-cache
export LLM_CACHE_DIR=                     # ...or relocate them
export LLM_BACKOFF_BASE_SECONDS=1         # wait between attempts; capped at 30 s
```

Every model call now goes through `pipeline/llmcall.py`: a rate-limited or unreachable endpoint
backs off and retries instead of aborting the run, a model that refuses `response_format:
json_object` is asked again without it, and an answered request is never re-sent. **Probe before
any batch run** — one call per question, and it tells you whether the model is usable at all:

```bash
python -m pipeline.scripts.probe_llm --image data/synthetic/dataset-v1/docs_img/APP-0001-aadhaar-1.png
```

## 8. Logs

The pipeline's own lines are one JSON object each, on stdout (`ts`, `level`, `logger`, `message`
plus context). uvicorn still prints its own plain-text startup and shutdown banner around them;
`--no-access-log` removes its per-request line, which this app logs itself:

```json
{"ts":"2026-09-27T10:33:30.077Z","level":"INFO","logger":"pipeline.api","message":"scrutiny completed","applicationId":"APP-95BAE08CA3","riskScore":27,"recommendation":"approve","checks":{"C1":"pass","C2":"pass","C3":"fail","C4":"pass","C5":"pass"},"flags":["C3"],"documents":1,"extractor":"template","adjudicator":"deterministic"}
```

- `pipeline.api.request` logs every request (`method`, `path`, `status`, `durationMs`).
- `pipeline.api` logs the two business events: `scrutiny completed`, `officer decision`.
- `pipeline.agent.report` logs a `warning` whenever a document could not be read or the
  adjudicator failed and the rule verdict was kept — the two places a silent fallback would
  otherwise look like a clean run.
- `pipeline.api.errors` logs every rejected request with its `code`.
- Applicant fields and document contents are never logged; `tests/test_logs.py` asserts it.

`PIPELINE_LOG_LEVEL=debug|info|warning` (default `info`) and `PIPELINE_VAR_DIR=/some/dir`
(relocate the JSON store) are read from the environment.

## 9. Eval harness and gate

From the repository root (the `eval` package is not installed, so `python -m eval.runner` must
run from here):

```bash
python -m eval.runner           # writes eval/reports/<timestamp>/{report.json,report.md}
python -m eval.gate; echo $?    # 0 = PASS, 1 = threshold breach, 2 = no report yet
```

`report.md` is the file the submission quotes, and it states the gate verdict itself rather than
leaving the table to be interpreted. Current result on dataset-v1: fail-flag precision 1.00 /
recall 1.00 (targets 0.90 / 0.85), mean ~0.1 ms per application offline.

`avgScrutinySeconds` is measured per application at the route (intake, extraction, rules,
adjudication, scoring, persistence) and kept in the store as `scrutinyMs`, which never goes on the
wire. It is not read from `modelMeta.latencyMs`: that field is an integer millisecond per the
contract, so the sub-millisecond pipeline rounds it to 0 and the dashboard shows "0.0 s". Measured
live on the demo slice: ~0.2 ms of pipeline work, ~5 ms mean per `POST .../scrutiny/run` over HTTP.

`GET /metrics/summary` reads `evalPrecision` / `evalRecall` from the newest
`eval/reports/<ts>/report.json` - the same newest-run rule `eval.gate` uses, so the dashboard and
the gate can never quote different runs - and omits both keys when no eval has run or the numbers
are unreadable (they are optional on the contract, and absent beats wrong). Nothing about them is
hardcoded: replace the newest report's numbers and the endpoint answers differently.

## 10. Where things live, and how to reset

| Path | What |
| --- | --- |
| `services/pipeline/var/applications/` | one JSON record per application, documents inline |
| `services/pipeline/var/reports/` | the latest `ScrutinyReport` per application |
| `data/synthetic/dataset-v1/` | generated corpus (regenerable, uncommitted) |
| `eval/reports/` | harness output (uncommitted) |

Reset local state at any time — nothing here is source:

```bash
rm -rf services/pipeline/var eval/reports data/synthetic/dataset-v1
```

## 11. Troubleshooting

- **`ModuleNotFoundError: pipeline`** — the venv is not active, or you did not run
  `pip install -e ".[dev]"` from `services/pipeline`.
- **`ModuleNotFoundError: generator`** — §2's second install was skipped; the corpus tests need it.
- **Corpus tests skip** — `data/synthetic/dataset-v1` is missing (§3) or `generator` is not
  installed (§2). `tests/test_agent_report.py` rebuilds the corpus into a temp dir when only the
  data is missing.
- **Two tracebacks per request in tests** — pytest was run from the repository root (§4).
- **A contract test fails on an unexpected key** — the response grew a field the frozen contract
  does not declare. Fix the model, not the contract; if the contract is genuinely short a path,
  draft `docs/change-requests/CR-<n>.md` and land it in a paired session (CR-1 is the worked
  example: Track A proposes and implements, Track B edits the contract).

## 12. Demo seed (integration step I2)

```bash
python -m pipeline.scripts.seed_demo            # from the repo root, venv active
```

Writes the first 20 dataset-v1 applications into the store - documents uploaded, scrutiny run,
statuses and timeline set - so the officer queue, metrics cards and a high-risk case all have
something to show:

```
seeded 20 applications into services/pipeline/var (cleared 0 from a previous demo seed)
  high risk (>=60): APP-0009, APP-0014, APP-0016
    APP-0009  riskScore 87
    APP-0014  riskScore 100
    APP-0016  riskScore 95
```

Deterministic (same corpus ids, same scores every run) and idempotent: it replaces only
generator-shaped ids (`APP-0001`..), so applications submitted through the API (`APP-<10 hex>`)
survive a re-seed. `--limit N` changes the slice size; `--root DIR` seeds somewhere else. Run it
from the repo root - it imports `pipeline`, which is installed, and reads the corpus files.

## 13. Live latency benchmark (integration step I4)

The eval harness answers "how good is the scrutiny"; this answers "how long does the officer
wait":

```bash
python -m pipeline.scripts.seed_demo --root /tmp/bench-store          # repo root
cd services/pipeline
PIPELINE_VAR_DIR=/tmp/bench-store uvicorn pipeline.api.main:app \
  --host 127.0.0.1 --port 8123 --no-access-log &
python -m pipeline.scripts.bench_scrutiny --base-url http://127.0.0.1:8123 \
  --sample 20 --repeat 5
```

It takes the applications `/officer/queue` lists that actually have documents (an empty
application answers 409), fires `POST .../scrutiny/run` at each, and reports min/p50/p95/max
against SPEC §2's 60 s target. Measured on 2026-09-27 over 100 runs: **p50 0.0030 s, p95 0.0032 s,
max 0.0037 s**, first call after a cold process 0.0056 s, while the server's own
`avgScrutinySeconds` said 0.0011-0.0013 s - the difference is HTTP, JSON and the store write.

Exit codes: 0 target met, 1 a run breached it, 2 nothing answering that port (or nothing filed to
score). `--json PATH` writes the summary plus every sample, including the `modelMeta` of the last
report, which is where the honest caveat lives: `extractor: template`, because this script runs
whatever the server is configured with and this server had no `LLM_API_KEY`. The model leg - up to
two calls per document behind a 30 s timeout - has only been timed against a local stand-in
endpoint (666 ms/application mean over `--limit 2`, see `docs/track-a/live-model-leg.md`); no real
vision model has been measured. Re-running appends scrutiny events to each application's timeline,
like the officer's "run again" does, so point it at a scratch store rather than a live demo one.
