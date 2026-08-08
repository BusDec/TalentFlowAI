# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

TalentFlow AI is a multi-tenant recruitment & talent intelligence platform built on **Django 6 + django-tenants (schema-per-tenant)**. It covers the talent lifecycle in phases: Phase I recruitment (advertisements → applications → BGV → roster/offer → panel), Phase II workforce planning, Phase III talent/skills. PostgreSQL is required (django-tenants cannot run on SQLite).

## Common Commands

```powershell
# Run the dev server (access via neepco.localhost, NOT 127.0.0.1)
python manage.py runserver 127.0.0.1:8000

# Migrations — django-tenants overrides `migrate`; use this instead
python manage.py migrate_schemas

# Seed demo data (run inside the tenant schema)
python manage.py tenant_command simulate_all --schema=neepco
# Individual sims: simulate_neepco_advt, simulate_roster_panel,
#   simulate_duplicates_consents, simulate_internal_posting,
#   simulate_workforce_planning, simulate_talent_data
python manage.py tenant_command simulate_roster_panel --schema=neepco

# Other management commands
python manage.py seed_staff_users          # accounts/
python manage.py import_profile_csv         # profiles/
python manage.py generate_sample_resumes    # recruitment/
python manage.py e2e_demo_flow             # recruitment/ end-to-end demo
python manage.py populate_neepco_real       # recruitment/ realistic NEEPCO data
```

Tests are currently only the Django default stubs (`tests.py` is a 63-byte placeholder in each app). Run with `python manage.py test <app_label>`.

## Architecture

**Tenant split (config/settings.py).** Two app groups:
- `SHARED_APPS` live in the **public schema**: `tenants`, `accounts`, plus Django contrib. `tenants.Client` (TenantMixin) and `tenants.Domain` (DomainMixin) define tenants; `accounts.User` is the internal HR/staff user (AbstractUser) with `UserTenantMembership` linking users to tenants with roles.
- `TENANT_APPS` live in **each tenant's schema**: `portal`, `consent`, `recruitment`, `profiles`, `workforce`, `talent`.

The DB engine is `django_tenants.postgresql_backend` with `TenantSyncRouter`. Tenant routing is by hostname via `TenantMainMiddleware` — the public schema maps to `localhost`, and each tenant maps to a subdomain (e.g. `neepco.localhost`).

**Two independent auth systems** (do not conflate):
- `accounts.User` (public schema) — internal staff/HR/admin, Django `AbstractUser`.
- `portal.CandidatePortalUser` (per-tenant schema) — external candidates, `AbstractBaseUser` with **email + simulated-OTP login** (Phase I). Auth backend: `portal.backends.CandidatePortalBackend`; candidate users have no perms/staff and are exempt from `accounts.middleware.TenantAccessMiddleware` (which otherwise requires an active `UserTenantMembership` for the current tenant).

**Agent system (`agents/`).** Every agent follows the same pattern: an **LLM-first implementation that deterministically degrades when no API key is set** (`agents/llm_client.py` checks `is_configured()`). Agents raise/forward `LLMClientError` and fall back to heuristics so everything works in demo mode. Provider is swapped purely via env vars (`LLM_PROVIDER`/`LLM_API_BASE`/`LLM_MODEL` in `.env`, DeepSeek default). Agents never auto-decide — they emit neutral facts / warnings for humans to act on (e.g. BGV compiles facts, roster agent warns but never blocks).

**Orchestration via signals (`recruitment/signals.py`).** `post_save` on `Application` auto-creates a `BackgroundReport` and fires `agents/duplicate_detection.flag_duplicates`; `post_save` on `Resume` triggers OCR/LLM parsing (`agents/resume_parser.py`) then scores each application via `agents/resume_evaluator.py`.

## Phase I Domain Flow (recruitment/views.py, recruitment/models.py)

`Advertisement` → `Post` (vacancies, `category_breakup` JSON) → `Candidate` (may map to a portal user) → `Application` (status stepper: received → document_verification → shortlisted → interview → offered → joined; `application_id` is sanitized on save). Supporting models:
- `Document` (candidate-uploaded) and `FetchedDocument` (DigiLocker — mocked via `DIGILOCKER_MOCK`).
- `BackgroundReport` (1:1 with Application) — neutral facts JSON the candidate explains and a human reviews.
- `RosterMatrix` (per-post, per-category UR/OBC/SC/ST/EWS with PwBD horizontal) + `CategoryAllocation` — `fills_slot=True` consumes a roster slot at offer time; `breach_warning` flags overfill. **Run `simulate_roster_panel` or a 500 occurs.**
- `PanelList` (ranked waitlist, auto-promotable to offer), `DuplicateFlag` (fuzzy match queue, human-resolved), `InternalJobPosting`/`InternalApplication` (employee mobility), `CommunicationLog`.

`recruitment/boilerplate.py` + `advt_pdf.py` generate advertisement text and PDFs. Frontend is Django templates + Bootstrap 5 + HTMX + Alpine.js (root `templates/`, per-app templates); the candidate portal is under `portal/` and is i18n'd (en + hi, compiled in `locale/`).

## Gotchas

- **Access via hostname, never `127.0.0.1`** — django-tenants routes by domain, so `neepco.localhost:8000` for the demo tenant, `localhost:8000` for public. A hosts-file entry already exists on this machine.
- `.env` is git-ignored and holds the only secrets (LLM key, DB creds). `.env.example` is the reference. Never put API keys in code or chat.
- `Post.category_breakup` is a JSON dict like `{"ur": 2, "ews": 0, ...}` — a distinct structure from `RosterMatrix` rows (which carry per-category vacancy counts and fill state).
- LLM features silently degrade to deterministic mode without a key — this is intended, not a bug.
- `SESSION_EXPIRE_AT_BROWSER_CLOSE = True`; logouts are POST forms (Django 6 requirement).
- `AUTH_USER_MODEL = accounts.User`; any new model referencing a user should point at `settings.AUTH_USER_MODEL`, not `auth.User`.
