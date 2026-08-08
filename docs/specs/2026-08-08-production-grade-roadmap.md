# TalentFlowAI — Production-Grade Roadmap

**Date**: 2026-08-08  
**Status**: Plan — pending implementation  
**Source**: Code audit + PM gap analysis across all app modules  
**Goal**: Transform the Phase I prototype into a govt-audit-ready, multi-tenant recruitment platform  

---

## Architecture Summary (Current State)

```
┌─────────────────────────────────────────────────┐
│ PUBLIC SCHEMA (shared)                           │
│  tenants.Client │ accounts.User │ UserTenantMembership │
│  django-tenants hostname routing (neepco.localhost)    │
├─────────────────────────────────────────────────┤
│ PER-TENANT SCHEMA (isolated)                     │
│  recruitment  │ portal │ profiles │ consent      │
│  workforce    │ talent │          │              │
│                                                  │
│  Two auth systems:                               │
│   - accounts.User (staff, public schema)          │
│   - portal.CandidatePortalUser (candidate, tenant)│
│                                                  │
│  Agent system: LLM-first → deterministic fallback │
│  Signals: post_save Application/Resume trigger    │
│           sync document parsing (blocking!)       │
└─────────────────────────────────────────────────┘
```

**Key files**: `config/settings.py`, `recruitment/models.py`, `recruitment/views.py`, `agents/*.py`, `portal/views.py`, `profiles/models.py`  
**Tests**: 63-byte stubs in every app — 0% coverage  
**LLM provider**: Pluggable via env vars (DeepSeek default), degrades gracefully without key  

---

## Code-Verified Gaps (What the PM Analysis Missed)

These were found by reading the actual source, not inferred from behavior:

| # | Finding | File:Line | Risk Level | Why It Matters |
|---|---|---|---|---|
| 1 | **RBAC defined, zero enforcement** | `accounts/models.py:20-28` roles exist; every `@login_required` in `recruitment/views.py` accepts any role | CRITICAL | A "viewer" can promote panelists to offer, modify rosters, or change any application status |
| 2 | **Aadhaar stored plaintext** | `profiles/models.py:29` — `aadhar_no = models.CharField(max_length=20, blank=True)` | CRITICAL | DPDP Act violation — encryption at rest is non-negotiable for PII |
| 3 | **Resume parsing blocks HTTP** | `recruitment/signals.py:30-57` — `parse_resume()` runs synchronously in `post_save` with Tesseract OCR at 200 DPI | CRITICAL | 30+ second page loads when candidate uploads a multi-page PDF |
| 4 | **Eligibility is a literal placeholder** | `agents/eligibility_verifier.py:73` — `"qualification": {"ok": None, "detail": "Manual review pending."}` | HIGH | The screening engine doesn't screen |
| 5 | **No age cut-off date field** | `recruitment/models.py:44` — only `max_age`; `eligibility_verifier.py:54` uses `closing_date` | HIGH | Sample ad shows 01-01-2026 cut-off ≠ 13-07-2026 closing — every age check is wrong |
| 6 | **Company profile per-advertisement, not per-tenant** | `recruitment/models.py:19-22` — `company_name`/`address`/`tagline` are per-Advertisement fields with NEEPCO hardcoded defaults | HIGH | Multi-tenancy is fake — every tenant's ads say NEEPCO unless manually overridden per ad |
| 7 | **Offer letter is plain text** | `recruitment/views.py:676-713` — `generate_offer_text()` returns `"\n".join(lines)` | HIGH | No PDF, no letterhead, no digital signature |
| 8 | **No application slip anywhere** | 0 references to "slip" in codebase | HIGH | The HOW TO APPLY boilerplate (`recruitment/boilerplate.py:58`) explicitly promises it |
| 9 | **DigiLocker fully mocked** | `recruitment/digilocker/client.py` — `DIGILOCKER_MOCK=True` in settings | MEDIUM | `FetchedDocument` model exists but real API integration doesn't |
| 10 | **No corrigendum model** | `recruitment/models.py` has no Corrigendum class | MEDIUM | Sample ad explicitly promises corrigenda on the website |
| 11 | **No email/SMS gateway** | 0 uses of `send_mail`; OTP is `print()` to console (`portal/views.py`) | MEDIUM | Candidates have no way to receive communications |
| 12 | **No advertisement approval workflow** | `recruitment/views.py:74` — `advertisement_create` is instant CRUD | MEDIUM | Govt ads need legal vet → reservation cell → competent authority sign-off |
| 13 | **No interview scheduling model** | Only `agents/interview_copilot.py` exists (question generation) | MEDIUM | No panel constitution, slot scheduling, invite, or score aggregation |
| 14 | **Advertisement PDF is styled like a SaaS landing page** | `recruitment/advt_pdf.py` — indigo palette, boxed sections, rounded corners | MEDIUM | Looks nothing like a govt notice — sample `1782823840.pdf` is plain, formal |
| 15 | **No post-based roster register** | `RosterMatrix` is per-post, not a persistent DOPT 100-point roster | MEDIUM | Reservation Act compliance requires a roster that survives across cycles |

---

## Phase 1 — Critical: Cannot Go Live (Weeks 1–4)

> **Outcome**: Passes a basic security audit. All critical vulnerabilities closed.

### 1.1 RBAC Enforcement

**Target files**: `accounts/models.py`, all `*views.py` across apps  
**Now**: 7 roles (super_admin, org_admin, hr_manager, recruiter, reviewer, auditor, viewer) defined in `UserTenantMembership.ROLE_CHOICES`. Zero views check them.  
**What to build**:
- Reusable `@require_role(*roles)` decorator that reads `request.user.tenant_memberships` for active tenant
- Gate every mutation view: `application_detail` (status change) → hr_manager+, `roster_view` (allocation) → hr_manager+, `panel_promote` → hr_manager+, `offer_letter` (approval action) → org_admin+, `advertisement_create` → hr_manager+
- Auditor role: read-only across all views
- Separation of duties: the user who screens cannot offer; the user who verifies cannot approve
- Add `@require_role` to all 30+ views in `recruitment/views.py`, `portal/views.py`

### 1.2 PII Encryption

**Target files**: `profiles/models.py:29`, new `profiles/encryption.py`  
**Now**: `aadhar_no = models.CharField(max_length=20, blank=True)` — stored as typed.  
**What to build**:
- AES-256-GCM encrypted field (via `django-encrypted-model-fields` or `cryptography` library)
- Masked display: `display_aadhaar()` → `"XXXX-XXXX-1234"`
- Retention schedule: purge Aadhaar data 5 years post-recruitment closure
- Audit log: who viewed the unmasked Aadhaar, when, why
- Migration to encrypt existing data

### 1.3 Async Document Processing

**Target files**: `recruitment/signals.py:30-57`, new `recruitment/tasks.py`  
**Now**: `parse_resume()` + `evaluate_resume()` run synchronously in `post_save` signals. Candidate upload triggers 30s+ HTTP response.  
**What to build**:
- Redis + Celery task queue (or RQ for lighter footprint)
- `parse_resume_async(resume_id)` task
- Status polling endpoint: `GET /api/resume/{id}/parse-status`
- Immediate ack on upload → "Processing..." badge → result injected via HTMX
- Move ALL signal-triggered agents to tasks: duplicate detection, BGV compilation, resume evaluation

### 1.4 Recruitment Audit Trail

**Target files**: new `recruitment/audit.py`, new model in `recruitment/models.py`  
**Now**: All status/score fields are last-write-wins. No record of who changed what or when.  
**What to build**:
- `AuditEvent` model: `actor` (FK User), `application` (FK), `field_name`, `old_value`, `new_value`, `timestamp`, `reason` (text), `tenant_id`
- Signal or `save()` override to auto-log every status change, score update, allocation, verification
- Admin view: filterable audit log per application
- CSV export for RTI responses
- Immutable: no update or delete on AuditEvent rows

### 1.5 Test Foundation

**Target files**: every `tests.py` (currently 63-byte stubs)  
**Now**: 0% coverage.  
**What to build**:
- `pytest-django` + `factory_boy` fixtures
- Critical-path smoke tests:
  - Candidate: register → OTP → login → apply → upload docs → view status
  - Staff: create ad → create posts → view applications → run eligibility → roster → panel → promote → offer
  - RBAC: viewer cannot promote, recruiter cannot approve offer
  - Agent pipeline: resume upload → parse → evaluate → score stored on application
- Target: 60%+ coverage on `recruitment/`, `portal/`, `agents/`

---

## Phase 2 — High: Blocks Govt Adoption (Weeks 5–10)

> **Outcome**: Demo-able end-to-end hiring cycle with real document intelligence.

### 2.1 Per-Tenant OrgProfile

**Target files**: new model in `recruitment/models.py`, `recruitment/views.py`  
**Now**: `company_name`, `company_tagline`, `company_address` live on each `Advertisement` with hardcoded NEEPCO defaults (`recruitment/models.py:19-22`). Every tenant's ad says "NEEPCO, Shillong."  
**What to build**:
- `OrgProfile` model (one per tenant): `name_en`, `name_hi`, `tagline_en`, `tagline_hi`, `address`, `footer_motto`, `contact_email`, `website`, `sbi_epay_text`, `logo`
- Tenant onboarding wizard: create tenant → fill OrgProfile → first advertisement inherits it
- All advertisement text/PDF generators read from OrgProfile, not Advertisement fields
- Portal branding driven by OrgProfile (header, footer, colors)

### 2.2 Govt-Format Advertisement PDF

**Target files**: `recruitment/advt_pdf.py`, `recruitment/boilerplate.py`  
**Now**: `AdvtPDF` uses indigo palette, colored section bars, boxed post blocks — looks like a startup's landing page.  
**What to build (match sample `1782823840.pdf` exactly)**:
- Bilingual letterhead: company name in Hindi + English, tagline, address
- "Date:" on its own line (not inline with advt number)
- Advertisement number after COMPANY PROFILE section header
- Post blocks: label:value rows (Post Code:, Name of Post:, No. of Vacancies:, etc.)
- Bullet style: ➢ for lists, ❖ for sub-items
- Section order: COMPANY PROFILE → POST DETAILS → HEALTH → GENERAL CONDITIONS → HOW TO APPLY → REGISTRATION SCHEDULE
- Schedule table with columns: Event, Commencement Date, Closing Date
- Footer: company motto + "Page X of Y" on every page
- Fee text inside HOW TO APPLY (not separate section)
- Train new Hindi text generation (right now only portal UI has `hi` i18n)

### 2.3 Structured Eligibility Criteria + Engine

**Target files**: `recruitment/models.py` (Post model), `agents/eligibility_verifier.py`  
**Now**: `Post.qualification` is free text. `Post.experience_required` is free text. Engine returns `"Manual review pending"` for all qualifications.  
**What to build**:
- New `Post` fields: `min_education_level` (choice: X/XII/Graduate/PG/PhD), `min_percentage` (Decimal), `experience_years` (Integer), `required_certificates` (JSON list)
- Eligibility engine rewrite:
  - Age: check against `age_cutoff_date` (new field), not `closing_date`
  - Education: match level + percentage from parsed marksheets
  - Experience: years computed from parsed experience letters
  - Certificates: presence check against `required_certificates`
  - Category: fee exemption check
- Per-field verdict: `{field: "age", ok: true, detail: "28 years as on 01-01-2026 (max 35)"}`
- Overall verdict: Eligible / Not Eligible / Needs Manual Review
- Human override with mandatory reason text
- UI: color-coded verdict card with expandable per-field details

### 2.4 Document Intelligence Pipeline

**Target files**: `agents/resume_parser.py`  
**Now**: Always OCRs (200 DPI, no preprocessing). Single generic `SYSTEM_PROMPT`.  
**What to build**:

| Step | Current | Target |
|---|---|---|
| PDF text extraction | Always OCR | Try `page.get_text()` first; OCR only when empty |
| OCR DPI | 200 | 300 (govt docs need higher resolution) |
| Preprocessing | None | OpenCV: deskew, denoise, adaptive threshold, binarization |
| Languages | `eng` only | `eng+hin` (Hindi text in marksheets, caste certificates) |
| Doc type detection | Resume only | Classify: Resume, PAN, Aadhaar, Marksheet, Experience Letter, Caste Certificate |
| Per-type extraction | Single SYSTEM_PROMPT | Per-type schemas: PAN regex `[A-Z]{5}\d{4}[A-Z]`, Aadhaar 12-digit + name, Marksheet %+CGPA+university, Experience: org+dates+designation |
| Confidence | Single number | Per-field confidence: `{"name": 0.95, "dob": 0.72, "pan": 0.99}` |
| Validation | None | Format validators + cross-field consistency |

### 2.5 Autofill Application from Parsed Docs

**Target files**: `portal/views.py` (apply flow), new JS in `static/js/`  
**Now**: `Document.extracted_data` stored but never consumed. Candidate manually types everything.  
**What to build**:
- Upload documents → parse → pre-fill application form with parsed values
- "auto-filled ✓" badges on each pre-filled field (green border, checkmark)
- Candidate reviews and edits before submitting
- Per-field source attribution: "from PAN card" / "from Aadhaar" / "from resume"
- Checkbox: "I confirm the auto-filled information is correct"
- Cross-doc consistency warnings: "PAN name doesn't match Aadhaar name — please verify"

### 2.6 Application Slip PDF

**Target files**: new `recruitment/slip_pdf.py`  
**Now**: Nothing. The HOW TO APPLY text explicitly promises it.  
**What to build**:
- Downloadable PDF after successful application
- Contents: unique application ID (already generated), candidate name, post applied, date of application, fee payment status, document checklist status
- Print-friendly A4 layout
- "No document is required to be sent by post" footer

### 2.7 Offer Letter PDF

**Target files**: `recruitment/views.py:676-713` (rewrite)  
**Now**: `generate_offer_text()` returns `"\n".join(lines)` — plain text only.  
**What to build**:
- Formal PSU-style offer letter PDF with:
  - Company letterhead (from OrgProfile)
  - Reference number, date
  - Candidate name + address
  - Post offered, pay scale, location, period of engagement
  - Joining date + reporting instructions
  - Document checklist for joining
  - Digital signature placeholder
- Acceptance workflow: candidate views → accepts (with digital consent) → status → `joined`
- Employee number auto-generation on acceptance

---

## Phase 3 — Medium: Complete Product (Weeks 11–16)

> **Outcome**: Full govt recruitment lifecycle — vacancy creation through joining.

### 3.1 Vacancy Requisition → Approval Workflow

**New models**: `VacancyRequisition`, `RequisitionApproval`  
**Flow**: Cadre/Division indent → Finance concurrence → Reservation Cell certification (roster points) → Competent Authority approval → Advertisement published  
**Each step**: role-gated, timestamped, auditable, with comments  
**Rejection path**: return to originator with reason

### 3.2 Post-Based Roster Register (DoPT 100-Point)

**New model**: `PostBasedRoster`  
**DOPT-compliant**: 100-point cycle with LR/U/R pattern for UR/SC/ST/OBC/EWS  
**Persistent**: survives across multiple recruitment cycles  
**Liaison Officer**: certification workflow  
**Consumption**: each Post's `category_breakup` derived from roster, not manually entered

### 3.3 Fee Payment + Exemption Engine

**New**: Payment gateway integration (Razorpay or SBI ePay)  
**Rules engine**: Rs 500 for General/EWS/OBC; auto-exempt SC/ST/PwBD/ESM/female  
**Edge case**: SC/ST candidates applying for UR posts MUST pay (per boilerplate)  
**Outputs**: payment receipt PDF, reconciliation report (collected vs exemptions vs applications), audit trail  

### 3.4 Corrigendum Module

**New model**: `Corrigendum` (FK → Advertisement, version number, changes JSON, published_date)  
**Auto-notify**: all applicants who applied before corrigendum publication  
**Public display**: versioned on advertisement page with change highlighting  
**PDF**: corrigendum addendum PDF appended to original advertisement

### 3.5 Document Verification Workflow

**New model**: `DocumentVerification` (replaces `Document.is_verified` checkbox)  
**Flow**: Assign verifier → pending → verified/rejected → per-document comments → re-upload loop  
**Dashboard**: verifier workload, pending count, average verification time  
**Audit**: who verified what, when, with what comments

### 3.6 Email/SMS Notifications

**Target files**: `portal/views.py` (OTP), new `notifications/` app  
**Gateway**: email (SendGrid/AWS SES) + SMS (MSG91/Twilio) via env-configurable provider  
**Templates**: application acknowledgement, shortlist notification, interview schedule, offer letter, rejection, corrigendum notice, withdrawal confirmation  
**Real OTP**: replace `print()` with actual email/SMS delivery  
**CommunicationLog**: wire existing model to gateway; track delivery status

### 3.7 Interview Panel + Scheduling

**New models**: `InterviewPanel`, `InterviewSlot`, `InterviewScore`  
**Panel constitution**: internal members + external experts, sitting fee tracking  
**Scheduling**: slot creation, candidate self-selection or admin assignment, calendar invites  
**Scoring**: individual score sheets + consensus score, aggregation with normalization across multiple panels  
**Post-interview**: score entry → composite merit computation with weightage

### 3.8 Bias & Fairness Guardrails

**Target files**: `agents/resume_evaluator.py`, `agents/shortlist.py`  
**Protected-attribute exclusion**: strip name, gender, age, category from LLM prompts  
**Category-aware shortlist**: optional mode that respects category quotas during ranking  
**Adverse-impact dashboard**: selection rate by category, 4/5ths rule flag, statistical parity metrics  
**AI-decision audit log**: every LLM call logged with prompt, response, timestamp, model version

### 3.9 Court Case / Litigation Tracker

**New model**: `LitigationCase` (FK → Application/Post/Advertisement)  
**Track**: case number, court, petitioner, interim orders, final orders  
**Block appointments**: tag application under stay → prevent status progression  
**Timeline**: chronological case events with document uploads  

---

## Phase 4 — Low: Polish & Scale (Weeks 17–20)

> **Outcome**: Production-grade at scale, compliant with all statutory requirements.

| # | Item | Effort | Key Deliverables |
|---|---|---|---|
| 4.1 | WCAG 2.1 AA accessibility | 5-7d | Screen-reader support, keyboard navigation, color contrast (4.5:1), focus indicators, ARIA labels, skip links |
| 4.2 | Anti-abuse: rate limiting + CAPTCHA | 2-3d | Django-ratelimit on OTP/login/apply endpoints, reCAPTCHA on registration |
| 4.3 | Real DigiLocker integration | 5-7d | Replace mock client with real DigiLocker API, candidate consent-grant UI, document pull + verify |
| 4.4 | Aadhaar e-KYC (UIDAI AUA/KUA) | 7-10d | Identity verification via UIDAI registered AUA, Aadhaar XML/QR code verification |
| 4.5 | Medical examination workflow | 3-4d | Hospital empanelment, appointment scheduling, report upload, fitness certification |
| 4.6 | Police verification / character antecedent | 3-4d | District SP office routing, status tracking, escalation on delay |
| 4.7 | Probation + service bond tracking | 3-4d | Probation period + review dates + confirmation, bond execution + release + recovery |
| 4.8 | Newspaper ad text generation | 2-3d | Employment News + national + regional newspaper formatted text from structured ad data |
| 4.9 | NCS/Employment Exchange feed | 3-4d | Auto-publish vacancies to National Career Service portal, Employment Exchange notification |
| 4.10 | Data archival & tamper-evident storage | 3-4d | Closed recruitment archiving (5-10 year retention), hash-chained audit records, retrieval API |
| 4.11 | Cross-doc consistency checks | 3-4d | Resume name vs PAN name vs Aadhaar name vs registered name, DOB agreement across all docs |
| 4.12 | Grievance/appeal module | 5-7d | Candidate files grievance → auto-acknowledge → assign → investigate → resolve → timeline + status |
| 4.13 | Tie-breaking rules engine | 1-2d | Configurable: older candidate → higher qualification % → alphabetical name |
| 4.14 | Staff UI i18n | 3-4d | Extend Hindi translations to all staff-facing templates + admin |
| 4.15 | Joining report + HRMS cutover | 3-4d | Joining report with date/designation/pay fixation → employee master data → HRMS API/webhook |

---

## Explicitly Deferred (Phase II / Future)

These are out of scope until a tenant specifically requires them:

- **CBT/Exam platform**: admit card generation, test conductor integration, merit-list computation from exam scores
- **Video interview**: live/recorded video interview platform
- **Employee self-service**: leave, attendance, payslip, IT declaration
- **Workforce planning analytics**: the `workforce/` and `talent/` apps are stub models today — full implementation is Phase II
- **Internal job posting flow**: `InternalJobPosting`/`InternalApplication` models exist but views are minimal

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| django-tenants upgrade breaks schema isolation | Low | Critical | Pin version, test migrations on staging before production |
| LLM provider API changes/outages | Medium | High | Deterministic fallback already built; ensure all agents degrade gracefully |
| Aadhaar e-KYC licensing delays (UIDAI approval) | High | Medium | Phase 4 item — start application process in Phase 1; use DigiLocker as interim identity proof |
| Govt stakeholder changes requirements mid-build | Medium | High | Modular architecture; each phase ships independently demo-able |
| Single developer bottleneck | High | High | Design each phase as independent work packets agents can execute in parallel |

---

## Dependency Map

```
Phase 1 (Critical)
  RBAC ─────────────────────────────────────────────────────────────┐
  PII Encryption ───────────────────────────────────────────────────┤
  Async Processing ─────────────────────────────────────────────────┤
  Audit Trail ──────────────────────────────────────────────────────┤
  Tests ────────────────────────────────────────────────────────────┤
                                                                     │
Phase 2 (High)                                                       │
  OrgProfile ────────────────────────────────────────────────────────┤ depends on nothing in Phase 2
  Advt PDF ────────────── depends on: OrgProfile ────────────────────┤
  Eligibility Engine ─── depends on: Audit Trail ────────────────────┤
  Doc Intel Pipeline ─── depends on: Async Processing ───────────────┤
  Autofill UI ────────── depends on: Doc Intel Pipeline ─────────────┤
  Application Slip ───── depends on: OrgProfile ─────────────────────┤
  Offer Letter PDF ───── depends on: OrgProfile, Audit Trail ────────┤
                                                                     │
Phase 3 (Medium)                                                     │
  Vacancy Requisition ── depends on: RBAC ───────────────────────────┤
  Post-Based Roster ──── standalone ─────────────────────────────────┤
  Fee Payment ────────── depends on: Audit Trail ────────────────────┤
  Corrigendum ────────── depends on: Advt PDF, Notifications ────────┤
  Doc Verification ───── depends on: RBAC, Audit Trail ──────────────┤
  Notifications ──────── standalone ─────────────────────────────────┤
  Interview ──────────── depends on: Notifications, RBAC ────────────┤
  Fairness ──────────── depends on: Eligibility Engine ──────────────┤
  Court Cases ────────── depends on: Audit Trail ────────────────────┤
                                                                     │
Phase 4 (Polish) — all items independent, can run in parallel ───────┘
```

---

## Agent Execution Strategy

Each phase item below is annotated with parallelism markers:

- **[S]** = Standalone — no dependencies on other items in the same phase
- **[C:X]** = Chain — depends on item X in the same phase
- **[P]** = Parallelizable — can run concurrently with any item

### Phase 1 — Fire in parallel (all [S] or independent)

| Item | Marker | Key Files |
|---|---|---|
| RBAC Enforcement | [S] | `accounts/models.py`, all `*views.py` |
| PII Encryption | [S] | `profiles/models.py`, new `profiles/encryption.py` |
| Async Processing | [S] | `recruitment/signals.py`, new `recruitment/tasks.py` |
| Audit Trail | [S] | `recruitment/models.py` (new model), `recruitment/audit.py` |
| Test Foundation | [S] | all `tests.py` files |

### Phase 2 — Fire in waves

**Wave 1** (all [S]):
- OrgProfile, Doc Intel Pipeline, Eligibility Engine

**Wave 2** (depends on Wave 1):
- Advt PDF [C:OrgProfile], Autofill UI [C:Doc Intel], Application Slip [C:OrgProfile], Offer Letter PDF [C:OrgProfile]

### Phase 3 — Fire in waves

**Wave 1** (all [S]):
- Post-Based Roster, Fee Payment, Notifications

**Wave 2** (depends on Wave 1):
- Vacancy Requisition [C:RBAC from Phase 1], Corrigendum [C:Advt PDF + Notifications], Doc Verification [C:RBAC + Audit Trail]

**Wave 3**:
- Interview [C:Notifications + RBAC], Fairness [C:Eligibility Engine], Court Cases [C:Audit Trail]

### Phase 4 — Fire all 15 items in parallel

All Phase 4 items are independent of each other.

---

## Status Tracking

| Item | Phase | Status | Assignee | Started | Completed | Notes |
|---|---|---|---|---|---|---|
| RBAC Enforcement | 1 | ⬜ Pending | — | — | — | — |
| PII Encryption | 1 | ⬜ Pending | — | — | — | — |
| Async Processing | 1 | ⬜ Pending | — | — | — | — |
| Audit Trail | 1 | ⬜ Pending | — | — | — | — |
| Test Foundation | 1 | ⬜ Pending | — | — | — | — |
| OrgProfile | 2 | ⬜ Pending | — | — | — | — |
| Advt PDF | 2 | ⬜ Pending | — | — | — | — |
| Eligibility Engine | 2 | ⬜ Pending | — | — | — | — |
| Doc Intel Pipeline | 2 | ⬜ Pending | — | — | — | — |
| Autofill UI | 2 | ⬜ Pending | — | — | — | — |
| Application Slip | 2 | ⬜ Pending | — | — | — | — |
| Offer Letter PDF | 2 | ⬜ Pending | — | — | — | — |
| Vacancy Requisition | 3 | ⬜ Pending | — | — | — | — |
| Post-Based Roster | 3 | ⬜ Pending | — | — | — | — |
| Fee Payment | 3 | ⬜ Pending | — | — | — | — |
| Corrigendum Module | 3 | ⬜ Pending | — | — | — | — |
| Doc Verification | 3 | ⬜ Pending | — | — | — | — |
| Notifications | 3 | ⬜ Pending | — | — | — | — |
| Interview Panel | 3 | ⬜ Pending | — | — | — | — |
| Fairness Guardrails | 3 | ⬜ Pending | — | — | — | — |
| Court Case Tracker | 3 | ⬜ Pending | — | — | — | — |
| (15 Phase 4 items) | 4 | ⬜ Pending | — | — | — | — |

---

## Conventions for Agents

When implementing any item from this roadmap:

1. **Never break the existing LLM → deterministic fallback pattern** — every agent must work without an API key
2. **Never hardcode tenant data** — use `OrgProfile` (once built) or `django-tenants` schema context
3. **Every mutation view gets `@require_role`** (once RBAC is built)
4. **Every status/score change writes an AuditEvent** (once audit is built)
5. **All new models go in `TENANT_APPS`** (recruitment, portal, profiles, consent) unless they're cross-tenant
6. **Tests are mandatory** — every new feature ships with pytest coverage
7. **Run `python manage.py migrate_schemas` after any model change** — not `migrate`
8. **Access via `neepco.localhost:8000`** for tenant routes, `localhost:8000` for public schema
