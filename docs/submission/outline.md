# Submission mapping (expected output → artifact)
- Clearly defined use case → SPEC.md §1–3 (paste + 1-para summary)
- Solution architecture → ARCHITECTURE.md diagram + component table + invariants
- Implementation approach → phased pilot: P0 (2 services, synthetic evals, officer shadow mode) →
  P1 (registry adapters behind interfaces, real OCR vendor eval) → P2 (scale + multilingual);
  risks: OCR quality on low-res scans, LLM cost/approval latency, change management for officers
- Prototype/POC → repo link, demo video (I4), eval report.md numbers, screenshots (B9 wireframes + live)
Slides order: problem+numbers → demo video 90 s → architecture → eval table → pilot plan → ask.
Drafting: agent may draft sections FROM repo docs only; humans edit final prose.