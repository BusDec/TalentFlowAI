# Offer Letter PDF + Acceptance Flow (Phase 2.7)

**Date**: 2026-08-08 · **Status**: Approved design (Wave 2) · **Source**: roadmap §2.7

## 1. Problem
`generate_offer_text()` returns plain text; no PDF, no reference number, no candidate acceptance flow, no employee number.

## 2. Goal
Formal PSU-style offer PDF + a candidate acceptance flow that moves status to `joined` and auto-generates an employee number.

## 3. Offer PDF (new `recruitment/offer_pdf.py`)
Replaces the plain-text render in the staff `offer_letter` view (the staff page now streams a PDF download; the text generator stays for email use).
- OrgProfile letterhead; `Reference No: <ADVT>-<application_id>-<yyyy>`; `Date`.
- Candidate: name + address (from CandidateProfile permanent_address when present).
- Body: post, pay scale, location, period of engagement, probation line, document checklist for joining (id proof, degree, experience certs, medical fitness), joining/acceptance instructions.
- "Digital signature placeholder" line: `(Authorised Signatory) — digitally signed copy to follow`.
- Footer: motto + Page X of Y.

## 4. Acceptance flow (portal)
- `portal/views.py`: `accept_offer(request, application_id)` — `@require_portal_user`, owner-check; GET renders the offer text + accept form (checkbox "I accept the offer of appointment" + optional note); POST requires the checkbox, sets `application.status = "joined"`, generates `employee_number`.
- **Employee number**: `f"{advt.post.advertisement.company_code or 'EMP'}-{post.post_code}-{seq:04d}"` where seq = count of joined applications for that post + 1 (deterministic; race-tolerant via retry on unique collision is unnecessary — employee_number is not unique-constrained, keep simple; documented).
- Status transition writes the standard AuditEvent via `Application.save(audit_actor=...)` — actor is None (candidate-initiated) but the reason field records "candidate accepted offer" via the audit reason parameter of the save path? `Application.save()` audits status change automatically (existing) — acceptance is candidate-initiated so actor=None; add reason via log_audit call in the view with reason="candidate accepted offer".
- URL `portal/applications/<id>/accept/` (name `portal_accept_offer`); button on portal application_detail when status == "offered" (staff sets offered via panel promote as today).
- Owner check: application.candidate.portal_user must equal request.user.

## 5. Staff side
`recruitment/views.py offer_letter` — render `offer_pdf.OfferPDF(application).generate()` as a PDF download instead of the text page (keep `generate_offer_text` for tests/email).

## 6. Testing
- `test_offer_pdf_contains_data`: PDF text contains org name, candidate name, post, reference number.
- `test_accept_flow`: offered application → candidate POST accept without checkbox → 200 re-render (error); with checkbox → 302, status joined, employee_number non-empty.
- `test_accept_writes_audit`: AuditEvent for the status change exists.

## 7. Commands
`pytest -q` · E2E (offer_letter route: recruiter GET 200 → now a PDF download; E2E asserts 200 — still fine) · commit `Phase 2: OfferPDF — offer letter PDF + acceptance flow with employee number`
