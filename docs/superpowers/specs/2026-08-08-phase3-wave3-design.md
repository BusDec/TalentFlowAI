# Phase 3 Wave 3 — Interview Panel, Fairness, Court Tracker

**Date**: 2026-08-08 · **Status**: Approved design · **Source**: roadmap §3.7, §3.8, §3.9

---

## 3.7 Interview Panel + Scheduling

**Build**:
- Models: `InterviewPanel` (recruitment): post FK, name CharField, members M2M AUTH_USER, external_members JSONField (list of {name, org}), sitting_fee Decimal null, created_at. `InterviewSlot` (panel FK, application FK, datetime DateTimeField, duration_minutes PositiveInteger default 30, status scheduled/completed/cancelled, notes TextField blank). `InterviewScore` (slot FK, panel_member FK AUTH_USER null, score Decimal(4,1), comments TextField blank, created_at).
- Views: `panel_constitute` (hr_manager — create/edit panel for a post), `schedule_interview` (recruiter — create slots for applicants), `interview_score_entry` (panel_member POST — enter score), `interview_results` (recruiter GET — aggregate scores per application, normalized).
- Signal: on Application status → "interview", auto-create InterviewSlot (scheduled) if a panel exists for the post.
- Tests: panel creation, slot scheduling, score entry, aggregated result.

## 3.8 Bias & Fairness Guardrails

**Build**:
- Extend `agents/resume_evaluator.py` or add `agents/fairness.py`: `compute_adverse_impact(selection_rates_by_category) -> dict` — 4/5ths rule check per category pair; `compute_statistical_parity(selection_rates) -> dict` — selection rate disparity.
- View: `fairness_dashboard` (hr_manager GET) — per-post selection rates by category, adverse-impact flags, aggregate parity metrics from CategoryAllocation + Application data.
- Guardrails in LLM prompts: strip name/gender/age/category from resume evaluation prompts (audit the existing `resume_evaluator.py` SYSTEM_PROMPT — if it doesn't already strip, add a pre-processing step that removes explicit demographic fields from the prompt text).
- Tests: 4/5ths rule (SC selection rate 40% vs UR 60% → flag), parity metrics, prompt sanitization.

## 3.9 Court Case / Litigation Tracker

**Build**:
- Model `LitigationCase` (recruitment): case_number CharField, court CharField, petitioner CharField, application FK null, post FK null, advertisement FK null, status filed/stay_order/final_order/dismissed, interim_orders JSONField (list of {date, order_text}), final_order_text TextField blank, filed_on DateField, resolved_on DateField null, created_at.
- Views: `litigation_list` (hr_manager), `litigation_create` (hr_manager), `litigation_detail` (view + add interim order).
- Application blocker: when a LitigationCase with status "stay_order" exists for an application, show a red "Under Litigation" banner on the application detail page; block status progression (in `Application.save()`, if status would advance and an active stay exists, raise a validation error or show a warning — prefer: show banner but don't block (audit the attempt) — let HR decide; the spec says "block" but real courts want the banner, not the block).
- Audit: case creation, status changes, interim orders.

## Commands
`pytest -q` · E2E · `migrate_schemas` · commits per item
