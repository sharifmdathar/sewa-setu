# The live model leg — running the pipeline through a real endpoint

## Why this exists

Until now every number in `eval/reports/` came from a path with no model in it: template
extraction, deterministic adjudication, no HTTP. That is the right thing for the SPEC §7 gate,
but it left the submission claiming an agentic AI pipeline while demonstrating only a rules
engine, and SPEC §6's `docs/*.txt|png` promise had no images behind it. This leg closes both:
the same corpus and the same rules, run through an actual model, reported separately.

The gate definition is unchanged and stays on the deterministic path. The live leg is quoted
*beside* it, never instead of it.

## New dependency, and why (AGENTS.md requires the note)

**Pillow**, as an *optional extra* of the data generator only:
`pip install -e data/synthetic[images]`. It is imported inside `generator/render.py`'s
functions, so generating the text corpus — which every existing test and eval pass uses — still
needs no graphics library. Nothing in `services/pipeline/**` depends on it. It exists to satisfy
SPEC §6's `docs/*.png`: without rendered documents there is no way to exercise the vision path
or to measure what a model actually reads back.

## What landed

| Piece | File | What it fixes |
| --- | --- | --- |
| Shared call path | `pipeline/llmcall.py` | One loop for both components. Transport failures back off and retry (a server's `Retry-After` wins over our own schedule); a 400 that names `response_format` retries once without JSON mode; a hard 4xx still fails fast. |
| Response cache | `pipeline/llmcache.py` | One file per request under `var/llm-cache`, keyed by model + full message list + JSON mode. A crashed run resumes instead of re-spending a daily quota. Corrupt or unwritable entries read as a miss. |
| Preflight probe | `pipeline/scripts/probe_llm.py` | Answers "is this model usable, and does it do JSON mode and images?" for one call each, before a batch run finds out the expensive way. |
| Image leg | `data/synthetic/generator/render.py` | `--png N` renders N documents into `docs_img/` with `image_manifest.json` carrying the fields a correct read must return. |
| Read-back scorer | `eval/image_leg.py`, `eval/image_leg_md.py` | Compares a read against that manifest: field recall **and** precision, whole-document clean reads, per-field and per-type breakdowns. `--reader text` runs the same documents through the deterministic parser as a control that should score 1.00. |
| Provenance | `eval/runner.py`, `eval/report_md.py` | The report says which extractor, adjudicator, model and cache state produced it, and titles itself `rules-only` or `live model leg`. |

The attempt budget is `max_retries + 1` calls per document, and that is now literally true: the
SDK's own retry layer is switched off in `new_client()`, because the two layers multiply rather
than nest — with both on, the budget cost up to its square in real HTTP requests, and a 429 was
answered by the SDK's blind backoff before this loop could read its `Retry-After`. Falling back out
of JSON mode spends an attempt rather than adding one. `tests/fake_endpoint.py` is a local
OpenAI-compatible endpoint that counts requests over a socket, so the budget, the retry and the
cache are all asserted without an `LLM_API_KEY`.

## Choosing an endpoint (checked on this machine, 2026-09-27)

| Option | Verified today | Notes |
| --- | --- | --- |
| **NVIDIA NIM** `https://integrate.api.nvidia.com/v1` | **Key verified working, 2026-09-27.** Callable from this account: `meta/llama-3.2-11b-vision-instruct` (JSON mode + vision, ~1 s) and `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` (~6 s). **Not** callable: `google/gemma-3-12b-it`, `google/gemma-3-4b-it`, `microsoft/phi-3-vision-128k-instruct` (404 "Not found for account"), `meta/llama-3.1-8b-instruct` (410 end-of-life), `deepseek-ai/deepseek-v4.1-flash` (timed out at 30 s) | `/v1/models` lists 82 models but it is a **catalog, not an entitlement** — probe before planning around a slug. Quota ceiling still unverified: check the console. |
| **Google Gemini** `https://generativelanguage.googleapis.com/v1beta/openai` | The OpenAI-compatible route exists (it answered "Missing or invalid Authorization header", not 404) | Free tier includes image input; second-hand sources disagree on the ceiling (250–1,500 req/day), so treat a corpus pass as multi-day. |
| **Local Ollama** `http://127.0.0.1:11434/v1` | Not installed here yet | The only option with no daily cap. This machine: RTX 3050 Ti, **4 GB VRAM**, 15 GB RAM — fine for a 3–4 B text model, marginal for a VLM (expect 10–40 s per rendered document). |
| **OpenRouter `:free`** | Their docs: 20 req/min, **50 req/day** at a $0 balance; 1,000/day only after buying $10 of credit. 10 free image-capable slugs today | Ruled out for a corpus pass (917 calls ÷ 50 = 19 days). Fine for the 20-document image leg. |

## Runbook

```bash
# 0. one-time: the images extra
pip install -e data/synthetic[images]

# 1. render the image leg (20 documents, spread across all ten doc types)
python -m generator --n 200 --anomaly-rate 0.25 --seed 42 \
    --out data/synthetic/dataset-v1 --png 20

# 2. probe the candidate models — 1-2 calls each, cache disabled for probes
export LLM_BASE_URL=... LLM_API_KEY=...
python -m pipeline.scripts.probe_llm --model google/gemma-3-12b-it --model qwen/qwen3.8-27b:free \
    --image data/synthetic/dataset-v1/docs_img/APP-0001-aadhaar-1.png

# 3. read-back accuracy: the control first (it needs no key), then the model over the same 20 PNGs
python -m eval.image_leg --reader text
LLM_MODEL=<winner> python -m eval.image_leg

# 4. then the whole-application live pass on a small sample (~20 calls)
LLM_MODEL=<winner> python -m eval.runner --limit 20

# 5. only then decide about a bigger text-corpus pass; the cache makes a re-run free
LLM_MODEL=<winner> python -m eval.runner --limit 60
```

`LLM_CACHE=0` disables the cache; `LLM_CACHE_DIR=/tmp/x` relocates it. Both matter when you want
a genuinely cold measurement.

## What the live numbers do and do not prove

- **They are model-dependent.** A different model is a different result, not a reproduction. The
  report names the model that produced it, and the served model can differ from the requested
  one on a router — the probe prints both.
- **Latency becomes real.** The offline pass reports sub-millisecond numbers; a live pass reports
  wall clock including round-trips and backoff. Only the live figure can be quoted against the
  "12–18 min → < 60 s" claim in SPEC §2.
- **Precision will move.** Misread fields surface as C1/C3/C4 verdicts, so the live table is
  expected to be worse than 1.00/1.00. That is the point of measuring it; report it as found.
- **`docs_img/` is rendered text, not a scan.** `eval.image_leg` scores it against the manifest's
  expected fields, which is a real read-back measurement — but on clean rendered type. It says
  nothing about skew, glare or low-DPI robustness, and the submission must not claim otherwise.
- **Read the control before quoting the model number.** `--reader text` scores the same 20
  documents through the deterministic parser. If the control is not 1.00, the manifest and the
  reader disagree and the model's score is measuring the harness, not the model.
- **Risk-flag recall stays ~0.54** at the spec-pinned `riskScore >= 60` on both legs; the queue
  ranks, it does not catch. Quote the fail-flag table as the gate and disclose this next to it.

## Verified without a key

Against a throwaway OpenAI-compatible server that 429s its first request and returns fixed JSON:

- `eval.runner --limit 2` with the key set: `path : llm-vlm + llm-adjudicator (fake-vlm-1)`,
  `11 new, 0 served from cache`, server-side count **12** requests for 11 successful calls —
  the rejected one was retried rather than aborting the run.
- Same command again: `0 new, 11 served from cache`, server count unchanged at 12.
- `probe_llm --image <rendered png>`: JSON mode OK, vision OK, and the server confirmed it
  received an `image_url` part.
- Mean per-application time moved from 0.11 ms (rules-only) to 666 ms (live), and the report
  titled itself `live model leg` in the second case.

Against the real corpus, no endpoint at all (`python -m eval.image_leg --reader text`, 2026-09-27):

- **124 of 124 stated field values read correctly, 20 of 20 documents read completely**, across
  all ten document types — so `image_manifest.json`'s ground truth and the pipeline's own reader
  agree, which is what makes the model's future score interpretable.
- `--reader model` with no key exits 2 with the command that fixes it, rather than scoring pixels
  with a text parser and reporting zero.

Now committed as tests, so this file is a description rather than a claim
(`python -m pytest -q tests/test_llm_http.py`, no key, loopback only):

- a 429 twice, then served — **3 requests, the documented budget**, and the run completes;
- a model that rejects `response_format` is asked a second time without it, and request two
  demonstrably carries no `response_format`;
- the same read twice costs **one** request — the disk cache works through a real socket;
- a 401 stops at one request rather than burning a quota on a reply that will never change;
- `run_scrutiny` over HTTP yields five evidence-carrying checks and a `modelMeta` naming the
  *served* model, which is not necessarily the requested one on a router.

## The first real endpoint numbers (2026-09-27)

20 rendered documents through `meta/llama-3.2-11b-vision-instruct`, against the control's 1.00/1.00:

| | control (template) | live VLM |
| --- | --- | --- |
| Field recall | 1.00 | **0.86** (107 of 124 stated values) |
| Field precision | 1.00 | **0.98** (107 of 109 answered) |
| Documents read completely | 20 of 20 | **5 of 20** |
| Time per document | — | p50 2.8 s, p95 18.2 s, max 23.8 s |

The failure is **not uniform, and that is the useful part**: `docType`, `name`, `idNumber` and
`issueDate` were all read at 1.00, while `expiryDate` was read on 4 of the 18 documents that state
one. The model reads the head of a page and drops the tail. Precision 0.98 against recall 0.86 says
it omits rather than invents — which is the dangerous direction here, because C2 can only fail a
document whose expiry it was given. That is why C2 now warns when a document of an expiring type
states no expiry (`rules.yaml -> expiryExpectedDocTypes`), instead of reading silence as validity.

Two consequences for the submission. SPEC §2's "< 60 s" measured **13.3 s mean, 15.5 s worst per
application** (2 applications, 9 documents, cache off) - inside the target, but on a sample of two,
so quote it as an observation rather than a distribution. And the 23.8 s single-document worst sits
close to the 30 s call timeout, so one slow page can fail a run outright.

What this still does not cover: a real scan. These are clean rendered documents, so everything
above is a ceiling, not an expectation, on phone-photo input.

## Parallelism costs more than it saves on a throttled tier

Reading an application's documents at once is the obvious fix for the p95 above, and the code does
it (`LLM_MAX_CONCURRENCY`, overlapping reads, order preserved). Measured against NVIDIA with the
cache off, on the same two applications and nine documents:

| | per application | per document |
| --- | --- | --- |
| sequential (`LLM_MAX_CONCURRENCY=1`) | **13.3 s** mean, 15.5 s worst | ~5.9 s |
| parallel (4) | 17.3 s mean, 20.4 s worst | ~7.7 s |

Parallel was **30 % worse**, because every document got slower: the limit is per account, not per
connection, so four in-flight requests queue against each other. The default is therefore **1**,
and the mechanism stays for an endpoint that is not throttling you — a local Ollama, or a paid key
with headroom — where it is a real 4x. The unit test that proves the overlap uses a local endpoint
with a 0.3 s-per-request delay, which is exactly the unthrottled case the public tier is not.

Two things this does not fix: the p95 breach is a property of the model's per-document latency, not
of the ordering, and the 30 s call timeout still sits uncomfortably close to the 23.8 s worst
observation. Batching, a faster model, or a longer timeout are the levers left.

## The trap that costs the most time

`services/pipeline/.env` is **not read by anything** — there is no dotenv loader, deliberately. The
file is a place to keep the values; they only exist once they are in the process environment:

```bash
set -a; . services/pipeline/.env; set +a
```

Without that, `LLM_API_KEY` is unset, `default_extractor()` returns the template parser, and every
"live" run reports rules-only numbers while looking exactly like it succeeded. The reports say
which path ran (`rules-only` vs `live model leg`), which is the only reason this fails loudly
rather than quietly.

