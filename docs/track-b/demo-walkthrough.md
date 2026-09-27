# Track B — demo walkthrough (recording script)

Presenter's click-by-click companion to `docs/demo/script.md` (the talk track).
Target: **5:00**, live against the real Track A API. Follow the beats in order;
each lists **URL · action · what you should see · say**. Prep the pre-flight
before you hit record.

## Pre-flight (do NOT record yet)
1. **Track A API up:** `cd services/pipeline && uvicorn pipeline.api.main:app --port 8000`
   → `curl localhost:8000/healthz` = `{"status":"ok"}`.
2. **Seed data:** `python -m pipeline.scripts.seed_demo` (20 apps; top risk is
   **APP-0014 = 100**, then APP-0016 = 95, APP-0009 = 87). Optional
   `--limit 26` to also show the duplicate-hash pair (APP-0009 / APP-0026) for the
   fraud beat.
3. **Track B in real mode:** `apps/web/.env.local` = `API_MODE=real` +
   `API_BASE_URL=http://localhost:8000`; `cd apps/web && npm run dev` → :3000.
4. **Upload fixtures ready** (the pipeline parses `KEY: value` text — a random file
   is flagged unreadable). Save these three as `.txt`:
   - `aadhaar.txt` → `DOC_TYPE: aadhaar` / `FULL_NAME: Priya Sharma` / `AADHAAR_NUMBER: 1234-5678` / `DATE_OF_BIRTH: 1992-03-14`
   - `bank_statement.txt` → `DOC_TYPE: bank_statement` / `FULL_NAME: Priya Sharma` / `AADHAAR_NUMBER: 1234-5678` / `ANNUAL_INCOME_INR: 180000`
   - `revenue_record.txt` → `DOC_TYPE: revenue_record` / `FULL_NAME: Priya Sharma` / `AADHAAR_NUMBER: 1234-5678` / `ANNUAL_INCOME_INR: 180000`
5. Browser at **1280×800**, 100% zoom, two tabs: **Tab A = citizen**, **Tab B = officer**.
6. Do one dry run of beats 1–3 so timings feel natural, then restart the server for a
   clean store and start recording.

---

## 0:00 — Hook
- **URL:** `http://localhost:3000/`
- **See:** "Sewa Setu Scrutiny POC", the brand mark, role switcher top-right.
- **Say:** *"12–18 minutes of manual scrutiny per application. Watch the agent do it in about 40 seconds — and every call it makes is explainable."*

## 0:30 — J1 · Citizen applies (`/citizen`)
- **Tab A →** `http://localhost:3000/citizen`. **See:** 3 service cards (Income, Caste, Residence).
- **Click** *Income Certificate* → apply form (Step 2 of 4). **Fill:**
  Full name `Priya Sharma`, DOB `1992-03-14`, Annual income `180000`, plus the
  remaining required fields (Aadhaar `1234-5678`, gender, guardian, village/ward,
  district, state, occupation).
- **Click** *Submit application* → **See:** redirect to the upload step (Step 3 of 4), checklist of the 3 required doc types.
- **Upload** the three `.txt` fixtures (one per doc type). **See:** each row ticks to "uploaded".
- **Say:** *"Synthetic data only, by design — no real PII anywhere."*

## 1:30 — J2 · System scrutinises
- **Tab A:** click **Check my application**. **See:** button shows busy, then the timeline (Step 4 of 4) grows a `scrutiny_done` event with a risk score + recommendation.
- **Say:** *"The pipeline extracts each document, runs five checks, and scores risk — all in under a second."*
- (The full evidence lives on the officer report — next beat.)

## 2:30 — J3 · Officer triages (`/officer`)
- **Tab B →** `http://localhost:3000/officer`. **See:** queue sorted by risk, **APP-0014 (100)** at the top in red.
- **Click** *Open report* on the top app. **See:** risk strip (100, high), the five checks expanded — point at **C5 fraud signals** (e.g. duplicate document hash) and **read its evidence + plain-language explanation aloud**.
- **Optional flourish:** open the **Status** dropdown → tick **decided** → *Filter* to show closed work; then reset.
- **Decision panel (right):** choose **Request info**, add a note, click **Record decision**. **See:** green "Decision recorded" confirmation.
- **Say:** *"The agent recommends; the officer decides. It's flagged high-risk, so she asks for the applicant to re-confirm."*

## 3:30 — J4 · Citizen sees the outcome
- **Tab A** (the citizen's app): **re-focus the tab** (this triggers an immediate status poll). **See:** a banner + a timeline entry for the officer's decision.
- **Say:** *"Back on the citizen side, the decision lands in their status feed — no email, no refresh roulette."*

## 4:00 — Dashboard (`/officer/dashboard`)
- **Tab B →** `http://localhost:3000/officer/dashboard`. **See:** cards (Total / Pending / Decided / **Avg scrutiny** / Flag rate), the two charts (Applications by day, Risk distribution) now fed by the metrics series, and the eval line: **precision / recall from `eval/reports/latest/report.md`**.
- **Say:** *"Programme-level view — and the offline eval numbers come straight from the harness report, so what's on screen is what's in `report.md`."*

## 4:40 — Close
- **Say:** *"Agent recommends, officer decides — explainable at every step. Roadmap: real registry adapters behind the same interfaces, a vetted OCR vendor, multilingual, and mobile. That's Sewa Setu."*
- **Stop recording.**

---

## If something breaks (fallbacks)
- **Live scrutiny slow / API down:** jump to a **pre-seeded** app (APP-0014) for J3 and narrate from there; the citizen flow (J1/J2) can be shown from an already-created app.
- **Browser/animation issue:** fall back to the **CLI rehearsal log** (the scripted J1→J4 run) + a **static screenshot** of a full scrutiny report — both are acceptable per the master script's fallback line.
- **Wrong numbers:** re-run `seed_demo` (idempotent) and refresh; the store is per-process, so a server restart resets to the seed.

## After the recording
- Save the video where `docs/demo/` expects it and reference it from the submission
  (`docs/submission/outline.md`).
- Tag the release: `git tag v1.0-poc && git push origin v1.0-poc` (I4 freeze).
