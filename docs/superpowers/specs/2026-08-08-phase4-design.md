# Phase 4 — All 15 Independent Items

**Date**: 2026-08-08 · **Status**: Approved design · **Source**: roadmap §4.1–4.15

All items are [S] (standalone). External integrations use mocks/stubs with env-gated real providers.

---

## 4.1 WCAG 2.1 AA Accessibility
Audit and fix: screen-reader support (ARIA labels on interactive elements), keyboard navigation (focus indicators), color contrast (4.5:1 minimum in talentflow.css), skip links. Files: templates, static/css. Tests: automated check (pa11y or lighthouse CI — skip if no npm; use manual ARIA audit instead).

## 4.2 Rate Limiting + CAPTCHA
`django-ratelimit` on OTP/login/register/apply endpoints. reCAPTCHA on registration (mock mode when RECAPTCHA_KEY absent). Files: portal/views.py (decorators), config/settings.py. Tests: rate-limit decorator applies; captcha mock mode works.

## 4.3 DigiLocker Integration
Replace mock in `recruitment/digilocker/mock.py` with real DigiLocker API client. Candidate consent-grant UI. Files: digilocker/client.py, portal consent view. Tests: mock client still works; real client raises NotConfigured when env absent.

## 4.4 Aadhaar e-KYC
UIDAI AUA/KUA integration. Files: new `aadhaar/` adapter. Tests: mock; real raises NotConfigured.

## 4.5 Medical Examination Workflow
Models: MedicalExam (hospital, date, report_file, fitness_status). Views: schedule exam, upload report, certify fitness. Tests: status flow.

## 4.6 Police Verification
Model: PoliceVerification (district, status, report). Views: initiate, update status. Tests: status flow + audit.

## 4.7 Probation + Service Bond
Model: ProbationRecord (start_date, end_date, confirmed_on, bond_amount). Views: staff tracking page. Tests: confirmation flow.

## 4.8 Newspaper Ad Text Generation
Generate Employment News / national / regional formatted text from Advertisement data. New `recruitment/newspaper.py`. Tests: output contains org name + post details.

## 4.9 NCS/Employment Exchange Feed
Adapter: publish vacancies to NCS portal (mock). Env-gated. Tests: mock works; real raises NotConfigured.

## 4.10 Data Archival & Tamper-Evident Storage
Archive closed recruitments (status=all joined/rejected + closing_date > 1yr ago). Hash-chain on AuditEvent rows (each row's hash includes previous row's hash). New `recruitment/archival.py`. Tests: archival eligible detection; hash-chain integrity.

## 4.11 Cross-Doc Consistency
Already built in Phase 2.4 (agents/doc_intel.py check_consistency). Surface on portal application detail + staff dashboard. Tests: warning renders.

## 4.12 Grievance/Appeal Module
Model: Grievance (candidate FK, subject, description, status filed/acknowledged/investigating/resolved, assigned_to FK null). Views: candidate files, staff resolves. Tests: status flow + notification.

## 4.13 Tie-Breaking Rules Engine
Pure function: `break_tie(candidates) -> ranked` with configurable rules (older → higher qual% → alphabetical). New `agents/tiebreaker.py`. Tests: deterministic ranking.

## 4.14 Staff UI i18n
Extend Hindi translations to staff-facing templates + admin. Add {% trans %} to recruitment templates. Tests: template renders with LANGUAGE_CODE=hi.

## 4.15 Joining Report + HRMS Cutover
Model: JoiningReport (application FK, joining_date, designation, pay_fixation, reported_to). View: candidate submits joining docs. Tests: report creation + status update.

## Commands
`pytest -q` · E2E · `migrate_schemas` · push after each batch of 5
