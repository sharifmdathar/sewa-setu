# Track A — pipeline design, decisions and eval summary

Written at the end of A9. Prompts A1–A9 are committed on `track-a`; this is the "why", not the
"what" — the code and `tests/` are authoritative for behaviour.

## Components

| Package | Entry point | Responsibility |
| --- | --- | --- |
| `pipeline/ingestion/` | `intake.stored_document`, `intake.to_content` | base64 upload → bytes → the record the store keeps and the `DocumentContent` extractors read; rejects undecodable uploads |
| `pipeline/extraction/` | `TemplateExtractor`, `LLMExtractor` | `DocumentContent` → `ExtractedFields`. Template parses the synthetic `KEY: value` form; LLM path is a VLM over any OpenAI-compatible endpoint, via `pipeline/llmcall.py` |
| `pipeline/rules/` | `run_rules(data, config)` | C1–C5 as pure functions over `ScrutinyInput`, tuned by `rules.yaml`; always exactly five checks, in order |
| `pipeline/agent/` | `run_scrutiny(application, documents)` | the orchestrator: extract → rule → adjudicate ambiguous checks → score → `ScrutinyReport`. Also owns `sha256_of_content` |
| `pipeline/agent/adjudicator.py` | `DeterministicAdjudicator`, `LLMAdjudicator` | settles `warn`/`info` checks into a final status plus officer-facing wording |
| `pipeline/llmcall.py` | `complete_json`, `new_client` | the only code that reaches a model: backoff-and-retry on transport failures, JSON-mode demotion, cache-aware, one attempt budget for both components |
| `pipeline/llmcache.py` | `ResponseCache`, `cache_for`, `combined_stats` | disk cache of completions under `var/llm-cache`, keyed by model + messages + JSON mode; a corrupt entry is a miss, never a failure |
| `pipeline/fraud/` | `score_fraud(data, checks, config)` | five mechanical features → `riskScore` (0–100), recommendation, flagged, and the internal signal list |
| `pipeline/store/` | `JsonStore` | one JSON file per record, atomic replace, process-wide lock |
| `pipeline/api/` | `create_app(store_root)` | the ten contract paths, service catalog, application state machine, queue, metrics |
| `pipeline/api/evalfeed.py` | `newest_eval_report`, `latest_eval_metrics` | reads the harness's newest `report.json` once, shared by `/metrics/summary` and `eval.gate` |
| `pipeline/logs.py` | `configure`, `event`, `warning` | one JSON object per line, context-carrying |
| `eval/` | `python -m eval.runner`, `python -m eval.gate` | offline pass over dataset-v1 vs ground truth, `report.{json,md}`, SPEC threshold gate |

### The flow one application travels

```
POST /applications            -> record {status: submitted}
POST /applications/{id}/documents
                              -> decode, sha256, append to record {status: documents_uploaded}
POST /applications/{id}/scrutiny/run
    ingestion.to_content      -> DocumentContent per stored document
    extraction                -> ExtractedFields (unreadable file -> empty fields, C3 reports it)
    rules.run_rules           -> five ScrutinyChecks, each with quoted evidence + explanation
    agent._adjudicate         -> only warn/info checks are re-decided; fail/pass verdicts untouched
    fraud.score_fraud         -> check points + signal points -> riskScore, recommendation
                              -> report persisted, {status: scrutiny_done}
POST /officer/decisions       -> {status: decided | info_requested} + officer timeline event
```

`riskScore = Σ weighted non-passing checks (weight × severity multiplier) + Σ distinct fraud
feature weights`, capped to 0–100 (SPEC §5: "weighted check outcomes + fraud signals"). The
double-count is deliberate: a check the mechanical features corroborate is worse than an
uncorroborated warning.

## Decisions, and why

**Check ownership is exclusive.** C1 owns name/ID divergence, C4 owns declared-vs-stated amounts
*except* whole-decimal-zero gaps, C5 owns duplicate hashes *and* those decimal-zero gaps
(`rules/numeric.is_power_of_ten_ratio` is the discriminator). One defect never lights up two
checks, which is what keeps the generator's labels unambiguous and the per-check numbers
meaningful.

**C2 does not warn about far-future expiry dates.** The corpus legitimately issues 10-year
documents, so that rule was a false-positive generator. C2 fails on expired / issued-in-the-future
/ expiry-before-issue and warns only on an implausible issuing authority.

**`asOf` is an input, not a clock read.** The corpus is pinned to 2026-06-30 (`ground_truth.json`);
the live API passes today's date. Without this, "expired" is unreproducible.

**The adjudicator only sees `warn` and `info`.** A rule that fired a hard `fail` has quoted values
as its reason; asking a model to reconsider it invites an overturn on a hunch. An
`AdjudicationError` keeps the rule verdict and logs a warning, so a broken endpoint degrades to
deterministic behaviour instead of failing the run.

**Adjudication rewrites status and explanation, never evidence.** Evidence is what the rules
found; it is the audit trail. Severity follows the final status (a `warn` settled to `pass` must
not stay `medium`), and an empty model explanation falls back to the rule's own text, so the
"every check has evidence + explanation" invariant cannot be broken by a model.

**`pipeline/fraud` deliberately re-declares the `recommendation` literal** instead of importing
it from `pipeline.agent.models`. Importing the agent package from fraud re-enters a
partially-initialised `pipeline.agent` when something imports `pipeline.fraud` first — a real
cycle. Two copies of a four-value contract enum is the cheaper problem, and
`test_the_adjudicator_status_options_are_the_contract_ones` plus the field-for-field model test
keep both honest.

**Documents live inside the application record, not their own collection.** `JsonStore` (A1)
validates collection names, and A7's scope excluded editing it. The record is a superset of the
contract's `Application`, and `application_view` is the only thing that leaves the process, so
`contentBase64` cannot leak onto the wire — `tests/contract.py` rejects undeclared keys anyway.

**Risk signals are computed but not served.** The frozen `ScrutinyReport` has no field for a
signal list (`modelMeta` declares exactly four properties, and the validator treats declared
properties as closed). Officers see them as `evidence` prose on C1/C5. If the dashboard wants
them as data, that is `docs/change-requests/CR-1.md`-style work for the integration phase — as is
any route for listing an application's documents, which the contract also lacks.

**`info_requested` counts as pending in `/metrics/summary`.** It leaves the officer queue but is
not a decision; the contract keeps the two statuses distinct for that reason.

**`flagRate` is over scrutinized applications**, not all of them — an application that has never
been run has no risk score to be a flag about.

**Errors are an envelope, not FastAPI defaults.** `{"detail": <str>, "code": <slug>}` from
`ApiError`, plus `fields[]` for request-body validation, and a catch-all that turns an unexpected
exception into the same shape. `code` is what Track B branches on: `unknown_service`,
`unknown_application`, `scrutiny_not_run`, `documents_required`, `invalid_document`,
`invalid_request`, `internal_error`.

**Nothing personal is logged.** Applicant fields and document bodies are exactly what a convenient
`logger.info(record)` would leak, so `tests/test_logs.py::test_no_log_line_contains_applicant_data`
asserts their absence across a full journey. Synthetic today; the habit is the point.

**Prompts treat documents as data.** `ADJUDICATION_SYSTEM_PROMPT` and the extraction prompt both
instruct the model to treat instructions found inside documents as content, never as commands —
the corpus documents are attacker-supplied text by construction.

## Eval summary

Pasted from `eval/reports/2026-09-27T10-35-06/report.md` (regenerate with
`python -m eval.runner`; numbers quoted in the submission must come from that file).

| Metric | Baseline (manual) | This run | Target |
| --- | --- | --- | --- |
| Fail-flag precision | unmeasured | 1.00 | >= 0.90 |
| Fail-flag recall | unmeasured | 1.00 | >= 0.85 |
| Mean scrutiny time / application | 12–18 min | 0.1 ms | < 60 s |

| Check | Support | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | 21 | 21 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| C2 | 12 | 12 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| C3 | 14 | 14 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| C4 | 6 | 6 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| C5 | 21 | 21 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| **all** | **74** | **74** | **0** | **0** | **1.00** | **1.00** | **1.00** |

Application-level risk flag at `riskScore >= 60`: precision 1.00, **recall 0.54**, accuracy 0.89,
F1 0.70 — 27 of 50 anomalous applications flagged, 0 false alarms.

### What these numbers do and do not prove

Read them narrowly. The corpus is generated from the same templates the rules are written
against, and its labels come from which field the generator perturbed — so 1.00/1.00 measures
**rule-and-label agreement**, i.e. that the checks fire on exactly what they are supposed to and
nothing else. It does not measure extraction robustness: nothing here exercises the VLM path,
because `LLM_API_KEY` was unavailable in every session (the 2 skipped tests are exactly that
branch).

The gap to close in integration is the OCR/VLM step: on real scanned documents the interesting
failure mode is a missing or misread field, which lands in C3/C1 as `info`/`fail` and would move
these numbers down. The risk-flag recall of 0.54 is the other honest weak point — single-anomaly
applications score 40–50 and stay under the spec-pinned flag threshold of 60, which is why the
queue's ordering by `riskScore` matters more than its cut-off. Threshold is fixed by SPEC §7, so
improving recall means richer scoring (A6 follow-up), not moving the goal posts.

**A live leg is now built and waiting on a key, not on code.** `docs/track-a/live-model-leg.md`
covers the endpoint options, the runbook and what the rendered `docs_img/` corpus does and does
not prove. The plumbing was verified against a local stand-in endpoint (a deliberate 429 was
retried, 11 calls cached and re-served without a second request), and `eval/report_md.py` now
titles each report `rules-only` or `live model leg` from the reports it measured, so the two can
no longer be quoted against each other by mistake.

## State and what integration still needs

- **Store**: per-process lock only. Two `uvicorn` workers would race on the same files; run one
  worker, or move to a real database (out of POC scope).
- **Auth**: none, by design (SPEC §3 — production auth is out, the demo uses a role switcher).
  Every path is unauthenticated; do not expose this port.
- **M4 landed (2026-09-27).** All three CRs are in. `shared/contracts/openapi.yaml` came from
  Track B's push (`5f28901`) and is now *theirs*: under M4 option A the contract and the dashboard
  are Track B's, Track A's landings are code-only, and `git diff origin/main..HEAD` over
  `shared/contracts/` is empty by design. Rebased local CR commits had re-added Track B's
  `MetricsSummary` block a second time — duplicate YAML keys that `safe_load` hides by keeping the
  last copy — so commit `take Track B's contract verbatim` restored their file. What Track A
  landed:
  - **CR-2** `queue()` returns every application with its `status` and `riskScore` (unscored = 0),
    and `metrics.pending` / `metrics.decided` both derive from `open_count()` over
    `OPEN_STATUSES`, so queue and cards can no longer disagree.
  - **CR-3** `applicationsByDay` (buckets of `createdAt`, oldest first) and `riskDistribution`
    (`<30 / 30–59 / >=60`, scrutinized applications only, same denominator as `flagRate`). Each is
    **absent when it has nothing to plot** — an empty array would draw a blank chart where "no data
    yet" is the truth; once any application is scored all three bands appear, so the axis is stable
    at zero as well as at three.
  - **CR-1** `GET /applications/{id}/documents` → `Document[]` in upload order, no bytes on the
    wire, judged by the live conformance suite and the coverage guard.
- **Track B's half of M4 is still open**: `types.ts` must declare the two series optional and the
  dashboard must read its charts from `getMetrics` rather than bucketing `getQueue`.
- **I2 seed**: `tests/corpus.py` and `eval/dataset.py` both read dataset-v1 into pipeline shapes;
  the seeding step can reuse either, but application ids from the corpus are what the store will
  hold, so keep them (`Repository.create` mints its own ids for new submissions).
- **I3 metrics**: already wired — `/metrics/summary` returns `evalPrecision` / `evalRecall` read
  from the newest `eval/reports/<ts>/report.json`, and returns neither key when no eval has run
  (the contract types them `number`, so absence beats null).
