# Submission draft — Sewa Setu agentic scrutiny (Track A input to M5)

Drafted from repo documents and measured runs only, as `docs/submission/outline.md` asks. Humans
edit the final prose. Every figure below carries its source; §7 is the provenance table, and
nothing in here is a number the repo cannot reproduce.

## 1. Use case (SPEC §1–3)

Manual scrutiny of a certificate application takes an officer ~12–18 minutes, is inconsistent
between officers, and misses forged, expired or mismatched documents. This prototype pre-scrutinizes
every application and hands the officer a ranked queue, a five-check `ScrutinyReport` where each
check carries its evidence and a plain-language explanation, and a recommendation — while the
decision stays with the officer.

In scope: extraction, checks C1–C5, risk score, recommendation, officer queue, citizen timeline,
metrics, eval harness, synthetic data. Out of scope by the spec: real registries and PII, payments,
mobile apps, production auth, multilingual UI.

## 2. Solution architecture

Mermaid diagram in `ARCHITECTURE.md`; component-by-component responsibilities and the reasoning
behind each choice are in `docs/track-a/pipeline-design.md` (15 recorded decisions). The shape:

Citizen UI → contract API (FastAPI, 11 operations) → extraction (template **or** VLM) → rules
engine C1–C5 (`rules.yaml`, versioned in the report) → adjudicator (`warn`/ambiguous only) → fraud
scorer → `ScrutinyReport` + riskScore + recommendation → JSON file store. Offline over the same
pipeline: the synthetic generator and the eval harness.

Code size as measured: 3,991 lines of pipeline, 1,829 eval, 1,052 generator, 5,108 test lines
across 247 + 32 tests. State and reporting are separate modules rather than one service class:
`pipeline/api/repository.py` performs transitions, `pipeline/api/readmodel.py` answers questions
about the records it wrote.

**Invariants that hold because they are tested**, not because they are documented: no check without
evidence and explanation; the agent never decides, only recommends; contract-exact responses
(a validator in `tests/contract.py` judges every response against `openapi.yaml` itself, in-process
and over a real socket); synthetic data only.

## 3. Implementation approach — phased pilot

- **P0 (what this repo is)** — two services, synthetic evidence, officer shadow mode. The pipeline
  runs beside the existing manual process; officers see the report and the queue but decide
  alone. Nothing here touches a registry, so the failure mode is a wrong recommendation an officer
  overrides.
- **P1** — a real OCR/VLM vendor chosen on measured accuracy, and registry adapters. To be exact:
  no registry interface exists in this repo yet. What exists is the pattern one would follow —
  `DocumentExtractor` is a `Protocol` with two interchangeable implementations (a template parser
  and an LLM-backed vision extractor), and which one runs is decided in `pipeline/config.py`, not
  at a call site. `pipeline/api/catalog.py` likewise keeps each service's required document types
  apart from the rules. `LLM_BASE_URL` points at any OpenAI-compatible endpoint, so no vendor is
  pinned.
- **P2** — scale and multilingual, which the store was never designed for (see §6).

**Risks worth stating rather than hiding:** OCR quality on low-resolution scans (the image leg has
never met a real scan — only clean text rendered to a PNG, and even that a live VLM read only 86%
of, with the misses concentrated in the last lines of the page), LLM cost and approval latency (a
per-document budget of `max_retries + 1` calls exists, a cost ceiling does not; measured p95 is
18.2 s per document, which is what puts the 60 s target in play), and change management for
officers — the queue's ordering is the thing they will argue with, and a 0.54 risk-flag recall
gives them reason to.

## 4. Prototype evidence

From `eval/reports/2026-09-27T15-55-07/report.md`, 200 synthetic applications, 917 documents, 50
with planted anomalies, seed 42, as of 2026-06-30:

| Metric | Baseline | Measured | Target |
| --- | --- | --- | --- |
| Fail-flag precision | n/a | **1.00** | >= 0.90 |
| Fail-flag recall | n/a | **1.00** | >= 0.85 |
| Application risk-flag recall | n/a | 0.54 (precision 1.00, accuracy 0.89) | disclosed, not gated |
| Scrutiny time / application | 12–18 min | see below | < 60 s |

Latency at four levels, because the honest answer depends on which one is being asked about:

| What was timed | Result | Source |
| --- | --- | --- |
| Pipeline in-process, offline, no HTTP, no store | 0.11 ms mean / 0.30 ms worst per application | eval report |
| The officer's actual wait on the rules-only path: `POST .../scrutiny/run` over HTTP, store writes included | **p50 3.0 ms, p95 3.2 ms, max 3.7 ms** (100 runs / 20 apps); 5.6 ms on the first call after a cold start | `pipeline.scripts.bench_scrutiny` |
| Same route with the server's own clock | 1.1–1.3 ms, so ~1.8 ms of the client figure is HTTP, JSON and the write | `/metrics/summary` |
| **One document through a live VLM** (`meta/llama-3.2-11b-vision-instruct`) | p50 2.8 s, p95 18.2 s, max 23.8 s. At the corpus mean of 4.6 documents per application that is **~13 s at p50 and ~83 s at p95** | `eval/reports/image-leg/2026-09-27T21-06-19` |

**Quote the second row for what this POC runs today, and the fourth for what a model in the loop
costs.** The 0.11 ms figure is real but it is not what anyone waits for. And the fourth row is the
one that puts SPEC §2's "< 60 s" in question rather than comfortably met: at p95 the model path
breaches it, and the 23.8 s worst observation sits close to the 30 s call timeout, so a slow
document can fail the run rather than merely delay it.

### Read-back accuracy, measured separately from judgement

`python -m eval.image_leg` compares what an extractor returns for each rendered
`docs_img/*.png` against the field values the generator wrote into it: field recall, field
precision (an invented value counts against the model, a blank one does not) and the
whole-document clean-read rate.

| Reader | Documents | Stated values | Correct | Clean reads | Time / document |
| --- | --- | --- | --- | --- | --- |
| deterministic template parser — the control, no model | 20 | 124 | 124 (recall 1.00, precision 1.00) | 20 of 20 | — |
| `meta/llama-3.2-11b-vision-instruct` over the same PNGs | 20 | 124 | 107 (**recall 0.86, precision 0.98**) | 5 of 20 (25%) | p50 2.8 s, p95 18.2 s |

The control row earns its place by being boring: it shows the yardstick and the ground truth
agree, so anything the model row says afterwards differs for reasons about the model.

**Where the model actually fails is not uniform.** `docType`, `name`, `idNumber` and `issueDate`
are each read at 1.00 — every identity field that C1 and C4 depend on. What collapses is
`expiryDate`: stated on 18 documents, answered on 4, recall 0.22. The model reads the head of a
page and drops the tail. Precision 0.98 confirms the direction: it almost never invents a value,
it omits one — which is the quieter and therefore more dangerous failure, because an omitted
expiry date reads as a document that cannot be expired.

## 5. Acceptance criteria (SPEC §8) status

| # | Criterion | Status |
| --- | --- | --- |
| 1 | J1–J4 end to end on the real API + the UI | **API half: verified twice** (`docs/track-a/i4-demo-rehearsal.md`). UI half is Track B's I1 checklist, not exercised from this session |
| 2 | Eval gate passes, numbers come from `report.md` | Done — `python -m eval.gate` exits 0, and §4 quotes that file |
| 3 | Every check rendered with evidence + explanation | API always emits both (asserted per check in tests); rendering unverified here |
| 4 | Officer decision updates the citizen timeline | Verified live: `info_requested` + a `decision_request_info` timeline event carrying the officer's note |
| 5 | Demo script rehearsed + fallback video recorded | Rehearsed **twice**, reproduced byte-for-byte. **Video not recorded** — it needs the Track B UI |

## 6. Limits a reviewer will find if they dig

- **The model leg has met a real model, and the honest numbers are worse than the table above.**
  Every scored number in §4 is still the rules-only leg: template extraction, deterministic
  adjudication. Over 20 rendered documents a live VLM read **107 of 124** stated field values
  (recall 0.86, precision 0.98) and completed only **5 of 20** documents without an omission, at
  p50 2.8 s / p95 18.2 s per document. Two consequences are carried through this draft rather than
  footnoted: the "< 60 s" claim of SPEC §2 holds at p50 (~13 s for a 4.6-document application) and
  **breaches at p95** (~83 s); and the field the model drops most (`expiryDate`, read on 4 of the
  18 documents that state it) is precisely the input C2 needs — which is why C2 now warns instead
  of passing when an expiring document states no expiry date.
- **The rules-only gate is unaffected by that change, and that is the point.** Re-running
  `python -m eval.runner` after the C2 change reproduces precision 1.00 / recall 1.00 / risk-flag
  recall 0.540 exactly: on the template path no document ever lacks an expiry it states, so the
  new warning fires only where a model failed to read one.
- **Risk-flag recall is 0.54 at the spec-pinned threshold of 60**, because single-anomaly
  applications score 40–50. The threshold is fixed by SPEC §7, so it was not tuned to flatter the
  metric. Per-check fail-flag precision and recall are both 1.00 — that is what the gate measures.
- **Perfect scores are partly by construction.** The corpus is generated from the same templates the
  rules read, and document text is attacker-supplied input by design; a 1.00 F1 on synthetic data
  is not evidence about real documents.
- **Single-process store.** One lock, JSON files: two uvicorn workers would race, and there is no
  auth on any port, so this is a demonstration service, not a deployable one.

## 7. Provenance — where each number comes from

| Figure | Command / file |
| --- | --- |
| precision/recall 1.00, recall 0.54, 0.11 ms | `python -m eval.runner` → `eval/reports/<ts>/report.md`; `python -m eval.gate` |
| p50 3.0 ms live | `python -m pipeline.scripts.bench_scrutiny --base-url http://127.0.0.1:8123 --sample 20 --repeat 5` |
| 200 apps / 917 docs / 50 anomalies / seed 42 | `python -m generator --n 200 --anomaly-rate 0.25 --seed 42` (SPEC §6) |
| 247 + 32 tests, ruff clean | `ruff check .` + `pytest -q` in `services/pipeline` and `eval` |
| read-back control (124/124, 20 of 20) | `python -m eval.image_leg --reader text` → `eval/reports/image-leg/<ts>/image_leg.md` |
| live VLM read-back (107/124, 5 of 20, p50 2.8 s) | `LLM_MODEL=meta/llama-3.2-11b-vision-instruct python -m eval.image_leg` → `eval/reports/image-leg/2026-09-27T21-06-19/` |
| 666 ms stand-in leg | `docs/track-a/live-model-leg.md`, verified with `eval.runner --limit 2` against a local fake |
| demo beats and payloads | `docs/track-a/i4-demo-rehearsal.md` (two passes, same store recipe) |

## 8. Slide order (outline's sequence, with the figure per slide)

1. Problem + numbers → 12–18 min/application, inconsistent, misses forgeries (SPEC §1).
2. Demo video 90 s → *pending I4 recording*; the static fallback is the APP-0014 report in
   `docs/track-a/i4-demo-rehearsal.md` (risk 100, C5 fail on a duplicate hash plus a 10× amount).
3. Architecture → `ARCHITECTURE.md` diagram, then the one sentence that matters: the contract is
   frozen and both tracks coded against it independently — CR-1/2/3 are the proof it worked.
4. Eval table → §4 above, with the 0.54 disclosed on the same slide as the 1.00.
5. Pilot plan → §3's P0/P1/P2.
6. The ask → a real document set and a vendor endpoint for P1; officer time to validate the
   recommendation format.
