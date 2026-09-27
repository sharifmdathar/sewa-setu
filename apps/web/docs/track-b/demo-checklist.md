# Track B demo checklist (B8)

Cold-start click-through on the mock. Target: **under 5 minutes**.
Prereq: `cd apps/web && npm run dev` → http://localhost:3000 (`API_MODE` unset → mock).

## 0. Boot (≤ 30 s)
- [ ] `/` landing renders with role switcher (Citizen / Officer).
- [ ] `/citizen` shows a skeleton briefly, then 3 service cards.
- [ ] `/officer` shows the queue: app-1002 (74) and app-1006 (68) on top —
      both flagged red; app-1004 shows `info_requested`.

## 1. Citizen applies end-to-end (J1, ≤ 2 min)
- [ ] `/citizen` → **Income Certificate** → **Apply now**.
- [ ] Fill: name `Test Citizen`, dob `2000-01-01`, income `5000`,
      address `1 Test Street` → submit → redirects to upload page.
- [ ] Upload **id_proof** and **income_proof** (any small text file) —
      each upload shows optimistic "uploaded" state + timeline grows.
- [ ] Press **Run scrutiny** → button busy ~1–1.5 s → "Scrutiny done",
      risk 25 (clean path), status badge → `scrutiny_done`.
- [ ] Status feed polls; timeline shows created → uploaded → scrutiny done.

## 2. Officer decides (J3, ≤ 1 min)
- [ ] `/officer/apps/app-1002` → report shows all 5 checks; C4
      `[field_mismatch]` + C5 `[duplicate_hash]` fail with evidence +
      explanation visible (never hidden).
- [ ] `/officer/apps/app-1006` → C2 `[expired_doc]` + C4 `[tampered_number]`.
- [ ] On the new app from step 1: approve with note `Demo approve` →
      success, status → `decided`.

## 3. Citizen sees the decision (≤ 30 s)
- [ ] Back on the app's page (or re-open via `/citizen/apps`): red banner
      "Officer decision: approve" appears within one 30 s poll — or press
      the refresh (visibility change on tab re-focus triggers an immediate
      poll).
- [ ] Timeline tail shows `decision_approved` with officer note.

## 4. Metrics & dashboards (≤ 1 min)
- [ ] `/officer/dashboard`: cards reflect the seed + the new decision
      (total ≥ 8, decided ≥ 2); **apps by day** chart spans 2026-09-19…22;
      **risk distribution** shows low/medium/high bars.
- [ ] Queue filter `?status=scrutiny_done` narrows the list; clearing it
      (link) restores; a filter matching nothing shows the empty state.

## Known demo edges
- Mock store lives in the dev-server process: restart = fresh seed.
- Chart data comes from `getQueue` until CR-1 lands (see
  `docs/change-requests/CR-1.md`).
