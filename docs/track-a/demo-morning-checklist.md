# Demo morning checklist — read this before you press record

Order matters. Steps 1 and 2 are the two ways this demo fails silently: a server running old code,
and a model in the loop turning a 3 ms call into a multi-second one.

## 1. Make sure the API is running current code

A uvicorn has been left on `127.0.0.1:8000` for the Track B human. If it has been up since before
the last merge, it is serving **old** rules and old report wording, and nothing on screen will look
wrong. Check its start time against the last commit:

```bash
ss -ltnpH 'sport = :8000'                                  # note the pid
ps -o pid,lstart,etime -p <pid>                            # when did it start?
git log -1 --format='%h %ci %s'                            # when did the code change?
```

If the process is older than the commit, restart it — **ask the Track B human first**, it is their
instance, and anything mid-request in their store will drop:

```bash
kill <pid>
cd services/pipeline && PIPELINE_VAR_DIR=$PWD/var \
  uvicorn pipeline.api.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

## 2. Do NOT have the model configured for the demo

`services/pipeline/.env` holds the NVIDIA key. It is read by nothing unless you source it, which is
exactly why this step exists: **leave it unsourced.**

| | rules-only (no key in env) | live model leg |
| --- | --- | --- |
| one scrutiny, over HTTP | p50 **3.0 ms** (measured, 100 runs) | **13.3 s mean, 15.5 s worst** per application (measured, 2 applications) |
| the script's "watch this take 40 seconds" | lands | 13 s of spinner per application |

```bash
env | grep '^LLM_' || echo "clean: no model in this shell"   # expect "clean"
```

If a shell has run `set -a; . services/pipeline/.env; set +a`, open a new one. The report's own
`modelMeta.extractor` is the tell: `template` means the fast path, `llm-vlm` means the model is on.

## 3. Re-seed immediately before recording

Seeded applications are scored against the corpus date (2026-06-30) while a live
`POST .../scrutiny/run` scores against today. Re-running scrutiny before the queue shot moves the
risk histogram — measured at `{low 17, medium 1, high 3}` becoming `{low 14, medium 4, high 3}` —
and the "27 of 50" story with it. Seed last, then do not re-run scrutiny on those applications.

```bash
python -m pipeline.scripts.seed_demo                       # default store
python -m pipeline.scripts.seed_demo --limit 26            # 26 applications, two shared-hash pairs
```

With `--limit 26` the seeded store contains both duplicate-document pairs — verified:
`APP-0009`/`APP-0014` share `8c7ce8117b88`, and `APP-0019`/`APP-0026` share `3a741271142b`. The
queue's top five, in order, are **APP-0014 100, APP-0026 99, APP-0016 95, APP-0009 87,
APP-0019 72** — all `reject` but the last, which is `manual_review`. The C5 beat narrates APP-0014
(risk 100, `reject`), whose evidence quotes that first hash.

## 4. Prove the beats in 30 seconds

This is the J2 narration check, run against current code. It prints the five explanations exactly as
the officer will see them, so the line you read aloud at 1:30 is the line on screen:

```bash
python - <<'PY'
import datetime as dt, json
from pipeline.agent import run_scrutiny
from pipeline.api.catalog import get
from pipeline.extraction import DocumentContent
from pipeline.rules import ScrutinyInput

required = list(get("income_certificate").required_doc_types)
declared = json.load(open("data/synthetic/dataset-v1/applications.json"))[0]["applicantFields"]
body = open("data/synthetic/dataset-v1/docs/APP-0001-aadhaar-1.txt").read()
body = body.replace("Unique Fictiona Identity Authority", "Corner Shop Printers")
report = run_scrutiny(
    ScrutinyInput(applicationId="APP-DEMO", serviceId="income_certificate",
                  requiredDocTypes=required, applicantFields=declared,
                  documents=[], duplicateSha256=[], asOf=dt.date.today()),
    [DocumentContent(documentId="D1", docType="aadhaar", fileName="scan.txt", text=body)])
for c in report.checks:
    print(f"{c.check_id} {c.status:5} {c.explanation}")
print("risk", report.risk_score, report.recommendation)
PY
```

Expected: C1 pass, C2 warn, C3 fail, C4 info, C5 pass, `riskScore 39`, `request_info`. C4 reads
`info` rather than `pass` because that application declares no monetary field — if it says `pass`,
you are on a different application and the numbers will differ.

**Decide the J2 story before you type it in the UI.** The verdict depends on the fields the citizen
beat enters, and the two options are different stories: declaring an income against APP-0001's
documents lights up C4 *and* C5 and returns **risk 99 `reject`**; leaving the income out returns
**risk 39 `request_info`**. Both are correct for the filing that was typed. Whichever you pick,
type the same values on take two, or the queue shot and the report shot will not agree.

The full twelve-call walk has been rehearsed three times against current code, most recently
2026-09-28 with the model environment unset: every call answered, all under 7 ms, and the
decision-to-timeline loop closed (`info_requested` plus a `decision_request_info` event carrying
the officer's note). Details in `docs/track-a/i4-demo-rehearsal.md`.

## 5. Confirm the gates before you quote any number

```bash
cd services/pipeline && ruff check . && python -m pytest -q && cd ../..
cd eval && ruff check . && python -m pytest -q && cd ..
python -m eval.runner && python -m eval.gate          # expect PASS: 1.000 / 1.000 / risk 0.540
```

## 6. Fallbacks, in the order they will be needed

1. **Live UI fails** → the static report in `docs/track-a/i4-demo-rehearsal.md` (APP-0014, risk 100,
   C5 fail on a duplicate hash plus an order-of-ten amount) is a complete, quotable artifact.
2. **API fails but the UI runs** → Track B's mock client answers every screen without a server.
3. **Numbers challenged** → `eval/reports/<newest>/report.md` is the file they come from, and it now
   titles itself `rules-only` or `live model leg`. The read-back table with real model numbers is
   `eval/reports/image-leg/2026-09-27T21-06-19/image_leg.md`.

## 7. What not to claim out loud

- The 3 ms figure is the **rules-only** path. With a model in the loop the honest figure is seconds,
  and at p95 the application breaches SPEC §2's 60 s target.
- The eval's 1.00 precision / 1.00 recall is rule-and-label agreement on a corpus generated from the
  same templates the rules read. Say that first, not when challenged.
- Application-level risk-flag recall is **0.54** at the spec-pinned threshold of 60. The queue ranks;
  it does not catch.
- The image leg is clean text rendered to a PNG, not a phone photo. Recall 0.86 is a ceiling.
- If asked "what does the model get wrong?", the honest and better answer is the measured one: it
  reads every identity field perfectly and returns `null` for the expiry on 14 of 18 documents —
  and asked in prose rather than JSON it states that expiry correctly. It has the value and will
  not commit it to the field. That is why the pipeline treats a missing value as a gap an officer
  must see (C2 warns) rather than as a passed check. Full write-up in
  `docs/track-a/live-model-leg.md`.
