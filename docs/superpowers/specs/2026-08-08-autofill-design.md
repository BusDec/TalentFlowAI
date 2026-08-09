# Autofill Application from Parsed Docs (Phase 2.5)

**Date**: 2026-08-08 · **Status**: Approved design (Wave 2) · **Source**: roadmap §2.5

## 1. Problem
`Document.extracted_data` (now populated by `parse_document_task`, Phase 2.4) is never consumed. Candidates type everything manually.

## 2. Goal
A two-phase apply flow: (1) candidate uploads resume + certificates → docs are parsed (eager in dev, Celery in prod) → the form renders **pre-filled** with parsed values, each with an "auto-filled ✓" badge and source attribution ("from PAN card", "from Aadhaar", "from resume"); cross-doc consistency warnings surface; (2) candidate reviews/edits and confirms with a checkbox before the application is created.

## 3. Two-phase apply (portal/views.py + templates/portal/apply.html + static/js/apply.js)

**Phase 1 — upload & parse** (GET, or POST with files when no parsed data yet):
- Candidate selects post, uploads resume (required) + certificate files (as today's fields).
- View parses via `doc_intel.extract_document` on each uploaded file (direct call — deterministic, no Celery latency in dev) and builds a `prefill` dict + `sources` map:
  - name/email/phone/dob ← resume `parsed_json` (full_name/email/phone/date_of_birth) + registered profile
  - pan ← certificate classified `pan` (fields.pan, fields.name)
  - aadhaar ← certificate classified `aadhaar`
  - qualification evidence ← marksheet classification (percentage/degree)
- Warnings: run `doc_intel.check_consistency([{doc_type, fields}...])` across resume/PAN/Aadhaar names; mismatches render an amber warning list.
- **No application is created in phase 1.** Parsed results cached in the session (`request.session["apply_prefill"] = {...}`) — session-only, no new models.

**Phase 2 — confirm & create** (POST with `confirm=on`):
- If `apply_prefill` in session, the form fields are pre-rendered (server-side) with values + badges + sources; candidate edits freely.
- POST requires: post_id, `declare=on` (existing), `confirm=on` ("I confirm the auto-filled information is correct" — only rendered when prefill exists; otherwise not required), resume file (existing), and the certificate files re-uploaded (files are not kept between phases — simplest; candidates re-select files in phase 2; documents are created at submit as today).
- On success: create Resume + Documents + Application exactly as today's flow; clear the session key.

**Session hygiene**: `apply_prefill` is per-advertisement (key includes advt id) and cleared on successful submit or on a new GET (reset).

## 4. Prefill mapping (exact)

| Form area | Source |
|---|---|
| registered name/email/phone | portal user (existing) — badge only when overridden by doc |
| DOB | resume date_of_birth or Aadhaar dob |
| PAN number | PAN doc fields.pan |
| Aadhaar number | Aadhaar doc fields.aadhaar (masked input, last 4 shown) |
| Education level/percentage | marksheet doc (percentage) |
| Cross-doc name warnings | check_consistency output |

Badges: `✓ auto-filled (from <source>)` styled `.tf-autofill` (green). Warnings: amber `.tf-alert warning` list above the form.

## 5. Testing (`portal/test_autofill.py`)
- `test_apply_phase1_parses_and_prefills`: POST files (resume txt with name/email/phone + PAN-cert txt) → 200, form contains parsed values + `auto-filled` badge text + no Application created.
- `test_apply_phase2_requires_confirm`: POST with `declare=on` but no `confirm=on` (when prefill session exists) → error, no Application.
- `test_apply_phase2_creates_application`: confirm=on → 302, Application + Documents created, session key cleared.
- `test_consistency_warning_shown`: resume name ≠ PAN name → amber warning text present.
- Existing `test_apply_flow` must still pass (no prefill session → confirm not required — backward compatible).

## 6. Commands
`pytest -q` · E2E (portal apply route behavior unchanged for the E2E's payload — E2E posts without files/session → confirm not required) · commit `Phase 2: Autofill — parsed-doc prefill with badges and consistency warnings`
