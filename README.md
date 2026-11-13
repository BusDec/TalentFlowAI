# TalentFlow AI

An agentic, multi-tenant recruitment and talent-intelligence platform built with
Django 6 and `django-tenants` (schema per tenant). It covers the full lifecycle:
advertisement → application → document verification → interview → offer →
joining → probation, plus workforce planning and talent/L&D.

## Live demo

**https://talentflow-ai-liard.vercel.app**

| Area | URL | Credentials |
|---|---|---|
| HR dashboard | https://talentflow-ai-liard.vercel.app/ | `admin` / `admin123` |
| Staff login | https://talentflow-ai-liard.vercel.app/login/ | `a.sharma` / `employee123` |
| Candidate portal | https://talentflow-ai-liard.vercel.app/portal/login/ | `rahul.sharma@example.com` (OTP shown on screen) |
| Public landing page | https://talentflow-ai-liard.vercel.app/landing/ | — |
| Health + OCR check | https://talentflow-ai-liard.vercel.app/health/ | — |

The demo is seeded with NEEPCO advertisement `NEEPCO/02/2026`, 12 posts,
70 candidates, 126 applications and sample records for every staff workflow.

## What is included

- **Recruitment:** advertisements, posts, applications, eligibility rules,
  resume scoring, shortlisting, document verification, fee reconciliation,
  DoPT rosters, panel lists and offer letters.
- **Interviews:** panels, slots, member-wise scores and aggregate results.
- **Post-selection:** joining reports, probation/bond tracking, medical exams
  and police verification.
- **Governance:** DPDP consent ledger, audit trail, duplicate detection,
  grievances, litigation tracker and vacancy requisitions with approvals.
- **Workforce and talent:** retirement forecasts, manpower requirements,
  recruitment batches, skills and training needs.
- **OCR:** Tesseract (English + Hindi) in the production container parses
  scanned PDFs and images; text-native PDFs use PyMuPDF.

## Run locally

Requires Python 3.12+, PostgreSQL 14+ and (for OCR) Tesseract.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # fill in DB values
python manage.py migrate_schemas --shared --noinput
python manage.py setup_tenant
python manage.py migrate_schemas --noinput
python manage.py seed_staff_users
python manage.py seed_cloud_data
python manage.py seed_portal_demo
python manage.py seed_demo_data
python manage.py runserver
```

Open **http://neepco.localhost:8000/** (not `127.0.0.1` — tenant routing is by
hostname). Add `127.0.0.1 neepco.localhost` to `/etc/hosts` if needed.

`seed_demo_data` is idempotent and fills every remaining workflow (documents,
payments, rosters, requisitions, interviews, litigation, probation, grievances,
medical/police checks, communications, audit history and notification
templates). Use `--no-files` to skip generated placeholder PDF uploads.

## Tests

```bash
pytest
```

## Deployment

The production demo runs on Vercel's container runtime with Supabase
PostgreSQL and Storage. The full setup, environment variables, schema layout
and verification checklist are in
[`docs/VERCEL_SUPABASE_DEPLOYMENT.md`](docs/VERCEL_SUPABASE_DEPLOYMENT.md).

Feature walkthrough and demo credentials:
[`TALENTFLOW_GUIDE.md`](TALENTFLOW_GUIDE.md).

## Notes

- Existing Supabase tables in `public.*` are untouched; TalentFlow uses
  `talentflow.*` (shared) and `tf_neepco.*` (tenant).
- The `talentflow-media` bucket is public-read for demo file URLs. Uploads and
  deletes require a private header enforced by RLS. Use private buckets and
  signed URLs for real candidate PII.
- Vercel limits request bodies to 4.5 MB.
- LLM agents run in deterministic mode until `LLM_API_KEY` is configured.
