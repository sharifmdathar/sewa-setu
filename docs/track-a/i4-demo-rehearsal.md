# I4 — demo rehearsal against the live API (Track A side)

`docs/demo/script.md` is a two-minute talk track over the *UI*, so this file rehearses the half of
it that Track A owns: the calls behind every beat, run for real against a local uvicorn, with the
responses and timings pasted as they came back. Nothing here is simulated — if a beat is missing,
it is because the UI, not the API, has to supply it.

Rehearsed 2026-09-27 on a scratch store, so the shared demo store and the Track B human's own
application were never re-scored or decided.

## How to reproduce

```bash
# 1. a scratch store, seeded deterministically from dataset-v1 (repo root, venv active)
python -m pipeline.scripts.seed_demo --root /tmp/bench-store

# 2. a second server, so port 8000 stays the shared demo instance
cd services/pipeline
PIPELINE_VAR_DIR=/tmp/bench-store uvicorn pipeline.api.main:app \
  --host 127.0.0.1 --port 8123 --no-access-log

# 3. the latency measurement the close of the script depends on
python -m pipeline.scripts.bench_scrutiny --base-url http://127.0.0.1:8123 --sample 20 --repeat 5
```

Exit codes: 0 target met, 1 a scrutiny breached the 60 s target, 2 nothing answering that port or
no application has documents. `--json PATH` writes the summary plus every sample.

## Beat by beat

| Script | API call | Observed live | UI owner |
| --- | --- | --- | --- |
| 0:30 "pick a service" | `GET /services` | 3 services; `income_certificate` requires `aadhaar`, `bank_statement`, `revenue_record`; 10 flat `fieldSchema` entries | B |
| 0:30 "3 fields" | `POST /applications` | 201 `APP-59F4F764AF`, status `submitted` | B |
| 0:30 "upload 2 docs" | `POST /applications/{id}/documents` ×2 | 201 `...-D1` `b4f97420b5e1`, 201 `...-D2` `ee435a068d33` | B |
| 0:30 (evidence panel) | `GET /applications/{id}/documents` (CR-1) | 200 `['aadhaar', 'bank_statement']`, no bytes on the wire | B |
| 1:30 "watch the scrutiny" | `POST /applications/{id}/scrutiny/run` | 200 in **4.0 ms**, `riskScore` 39, `recommendation` `request_info` | B |
| 2:30 "queue sorted by risk" | `GET /officer/queue` | 21 items, top three `100 / 95 / 87` = APP-0014, APP-0016, APP-0009 | B |
| 2:30 "point at C5" | `GET /applications/APP-0014/scrutiny` | C5 `fail` on a `reject` at 100, evidence quoted below | B |
| 2:30 "request_info" | `POST /officer/decisions` | 200 `{'applicationId': 'APP-0014', 'status': 'info_requested'}` | B |
| 3:30 "timeline + banner" | `GET /applications/APP-0014` | status `info_requested`; last timeline event `officer / decision_request_info` carrying the officer's note | B |
| 4:00 "eval numbers" | `GET /metrics/summary` | 21 applications, `avgScrutinySeconds` 0.00133, `evalPrecision` / `evalRecall` 1.0, 20 `applicationsByDay` buckets, `riskDistribution` `{low: 14, medium: 4, high: 3}` | B |

### The one explanation read aloud (1:30)

The incomplete filing is what the script's own citizen beat produces — 2 of 3 required documents:

```
C1 pass  Every document names the same person as the application, so identity is consistent.
C2 warn  An officer should look at this before deciding. The dates that were read are possible, b…
C3 fail  The evidence set is incomplete, so the claim cannot be verified without another document…
C4 pass  The figures the applicant declared are the same figures the documents state.
C5 pass  No reused document files or suspiciously padded amounts were found in this application.
```

**Re-quote before recording.** C2's sentence changed after this rehearsal was written: `fcf2582` made
an unread expiry a warning, and the follow-up made the wording name the *actual* cause, so the C2
line the presenter reads aloud is now:

> An officer should look at this before deciding. The dates that were read are possible, but the
> issuing authority is missing or does not match the office that should have signed it - check the
> paper before approving.

Verified against current code on a 2-of-3-document `income_certificate` filing: C1 pass, C2 warn,
C3 fail, C4 info (that application declares no monetary field, so there is nothing to cross-check),
C5 pass, `riskScore` 39, `request_info`. Reproduce it with `docs/track-a/demo-morning-checklist.md`.

### The fraud signal pointed at (2:30)

`APP-0014`, `riskScore` 100, recommendation `reject`, C5 `fail`:

> Forgery signals: APP-0014-fee_receipt-5.txt has hash 8c7ce8117b88 which also appears in another
> application; APP-0014-self_income_declaration-4.txt states 4240000, exactly an order of ten away
> from the declared 424000.

Two independent signals, one file name each, both traceable to a stored document the officer can
now fetch by name through CR-1's endpoint. This is the SPEC §8.3 "every check has evidence" line.

## Second pass, and the one thing that moved

SPEC §8.5 asks for the script to be *rehearsed*, so the whole walk ran again against a freshly
seeded scratch store (`/tmp/i4-run2`, port 8124) after the model-leg commit landed and changed
`pipeline/agent/adjudicator.py`. Same server code path, second store, later clock:

| Beat | Pass 1 | Pass 2 |
| --- | --- | --- |
| J1c document hashes | `b4f97420b5e1`, `ee435a068d33` | identical |
| J2 verdict | 200 in 4.0 ms, risk 39, `request_info` | 200 in 5.1 ms, risk 39, `request_info` |
| J2 five explanations | as quoted above | identical, wording for word |
| J3a queue | 21 items, 100 / 95 / 87 | 21 items, 100 / 95 / 87 |
| J3b C5 evidence | duplicate hash + order-of-ten amount | identical string |
| J3c/J4 decision + timeline | `info_requested`, `decision_request_info` | identical |
| 4:00 band histogram | `{low 14, medium 4, high 3}` | `{low 17, medium 1, high 3}` |

Every number the presenter reads aloud reproduced. The histogram is the one that moved, and it is
not noise: seeded applications are scored against the corpus's own `asOf` date (2026-06-30), while
`POST .../scrutiny/run` scores them against **today**, and the two dates put different documents
past their expiry. Pass 1's store had been through the latency bench, which re-ran scrutiny on all
20 applications. Verified on the pass-2 store: one bench pass took the histogram from
`{low 17, medium 1, high 3}` to `{low 14, medium 4, high 3}` - pass 1's exact numbers - with three
applications crossing from low to medium. `avgScrutinySeconds` moved for the related reason that it
averages only the runs recorded since seeding (0.00033 then, 0.0013 after), so the client-side bench
p50 is the figure to quote, not that one.

**Demo consequence:** whoever presents must not re-run scrutiny on the seeded applications before
the queue shot, or the histogram and the "27 of 50" story drift toward today's date. Either
re-seed immediately before recording, or record against a store that has only ever been seeded.

## Latency, measured over the wire

`python -m pipeline.scripts.bench_scrutiny --base-url http://127.0.0.1:8123 --sample 20 --repeat 5`
— 100 timed `POST .../scrutiny/run` calls against a running uvicorn, whole-store duplicate
scanning included, client-side clock:

| | value |
| --- | --- |
| p50 | **0.0030 s** |
| p95 | 0.0032 s |
| max (warm) | 0.0037 s |
| first call after a cold process | 0.0056 s |
| server's own `avgScrutinySeconds` | 0.0011–0.0013 s |
| against the SPEC §2 target | < 60 s, met by ~4 orders of magnitude |

The two clocks answer different questions and both belong in the talk: the pipeline takes ~1.2 ms,
a client round trip takes ~3 ms, so about 1.8 ms is HTTP, JSON and the store write. That is the
number to quote for "watch this take 40 seconds" — not the eval harness's 0.13 ms/application,
which is offline template scoring with no HTTP and no store.

**What this does not cover.** `LLM_API_KEY` was unset here, so the extractor was `template` and the
adjudicator `deterministic` — recorded inside the artifact's own `modelMeta`, on purpose. The model
leg has been timed, but only against a local stand-in OpenAI-compatible endpoint: 666 ms per
application mean over `--limit 2`, with a 429-and-retry in the sample
(`docs/track-a/live-model-leg.md`). No real vision model has been measured, so the demo must not
present any of these figures as what a scanned document costs — on a real endpoint, up to two model
calls per document sit between the officer and the answer, behind a 30 s timeout.

## What still blocks the full I4

1. **Nothing on the Track A side is unready**: every call the script narrates answers, in order,
   with contract-valid payloads, and the coverage/conformance suites are green against the same
   server (`pytest -q` → see `docs/track-a/pipeline-design.md`).
2. **The 90-second video and the screenshots are Track B's** — they need `apps/web` running against
   this API, which is their own configuration to make. Track A's obligation is only that the API
   answers on a known port with the payloads above. Track A cannot record their UI.
3. **A real endpoint has never answered for the model leg.** The demo narrates an agentic pipeline;
   the only model-leg timing is against a local stand-in server. If the audience asks "what does a
   scanned document cost?", the honest answer today is "not measured".
4. **`v1.0-poc` was not tagged.** A release tag is a shared, externally visible decision; it waits
   for the human. (The M4 commits themselves are on `origin/main` — pushed alongside the Track B
   landing, and a fresh clone now has the CR-1/2/3 behaviour the script narrates.)
