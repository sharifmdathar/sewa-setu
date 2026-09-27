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

The attempt budget is unchanged at `max_retries + 1` calls per document; falling back out of
JSON mode spends an attempt rather than adding one.

## Choosing an endpoint (checked on this machine, 2026-09-27)

| Option | Verified today | Notes |
| --- | --- | --- |
| **NVIDIA NIM** `https://integrate.api.nvidia.com/v1` | Catalog readable without a key: 82 models, image input on `google/gemma-3-12b-it`, `microsoft/phi-3-vision-128k-instruct`, `meta/llama-3.2-11b-vision-instruct`, `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | Quota **not** verified — their limits page 404s and 2026 forum traffic is people asking for the free tier to be raised. Check the console after signup before planning a run. |
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

What none of that covers: a real model's answer quality. The plumbing and the yardstick are both
proven; the numbers from a real endpoint are still to be produced.

