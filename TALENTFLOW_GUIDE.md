# TalentFlow AI — Recruitment & Talent Intelligence Platform

An agentic, multi-tenant recruitment portal built with **Django + django-tenants (schema-per-tenant)**. Covers the full talent lifecycle: recruitment → background verification → workforce planning → talent/L&D.

---

## 1. Access URLs

### NEEPCO Tenant (main demo)

| Page | URL | Notes |
|---|---|---|
| **HR Dashboard** | http://neepco.localhost:8000/
http://neepco.localhost:8000/ | Funnel stats, roster alerts, flags |
| **HR Login** | http://neepco.localhost:8000/login/ | Internal staff |
| **Django Admin** | http://neepco.localhost:8000/admin/ | Full data management |
| **Candidate Portal** | http://neepco.localhost:8000/portal/login/ | External candidates (OTP login) |
| **Candidate Register** | http://neepco.localhost:8000/portal/register/ | New candidate sign-up |

### Public Tenant (platform admin)

| Page | URL |
|---|---|
| **Platform Admin** | http://localhost:8000/admin/ |

> ⚠️ **IMPORTANT:** Access via `neepco.localhost` (NOT `127.0.0.1`). django-tenants routes by domain name. A hosts-file entry (`127.0.0.1 neepco.localhost`) has already been added on this machine.

---

## 2. Users & Credentials

### Staff / HR / Admin

| Username | Password | Role | Where |
|---|---|---|---|
| `admin` | `admin123` | Superuser (Org Admin) | NEEPCO tenant + Public schema |

### Sample Employees (for internal postings & talent map)

| Username | Password | Name |
|---|---|---|
| `a.sharma` | `employee123` | Amit Sharma |
| `r.mehta` | `employee123` | Ramesh Mehta |
| `s.iyer` | `employee123` | Sundar Iyer |
| `p.das` | `employee123` | Priya Das |
| `k.nath` | `employee123` | Kabita Nath |

### Sample Candidates (portal — OTP login)

| Email | Name | Notes |
|---|---|---|
| `rahul.sharma@example.com` | Rahul Sharma | Has applications |
| `sneha.reddy@example.com` | Sneha Reddy | Has applications |
| `arjun.patel@example.com` | Arjun Patel | Has applications |
| `priya.sharma@example.com` | Priya Sharma | Has applications |
| `vikram.singh@example.com` | Vikram Singh | Has applications |

**How candidate OTP login works (Phase I):**
1. Go to `/portal/login/`, enter the email.
2. A 6-digit **simulated OTP** is displayed in the page message (dev mode).
3. Enter it on the verify screen → logged in.

> No password needed in Phase I. Real OTP (email/SMS gateway) comes later.

---

## 3. Core Features

### Phase I — Intelligent Recruitment
- **Multi-advertisement intake** — candidate applies to posts across adverts
- **Visual funnel dashboard** — Received → Document Verification → Shortlisted → Interview → Offered → Joined (+ Employee Number)
- **Document verification** — PDF upload + (mock) DigiLocker fetch
- **Background Verification Agent** — compiles *neutral* tabulated facts; candidate explains; human reviews
- **Roster compliance (critical)** — UR/OBC/SC/ST/EWS + PwBD matrix per post, breach warnings before offer
- **Panel list** — ranked waitlist, auto-promote to offer
- **Duplicate detection** — fuzzy match (name/email/phone/DOB) across advertisements; human resolution queue
- **Internal job postings** — employees apply internally, priority flags
- **Interview co-pilot** — AI-suggested questions from JD + resume
- **Consent management (DPDP)** — purpose-limited consent ledger + immutable events + CSV export
- **Candidate portal** — register, apply, track, upload resume, respond to BGV flags, manage consents

### Phase II — Workforce Planning
- Retirement/attrition profiling (7-year heatmap)
- Manpower demand forecasting (project + separation driven)
- Lead-time-aware recruitment calendar (batches)
- (Simulated data: 7-year retirement forecast, 3 recruitment batches)

### Phase III — Talent Intelligence (foundation)
- Skills / competency map
- Training Needs Assessment (TNA)
- Training programmes catalogue
- (Simulated data: 12 skills, 5 training needs)

---

## 4. AI Agents (pluggable LLM)

All agents live in `agents/` and work **without an API key** via deterministic fallback. Add a key for full LLM behaviour.

| Agent | Module | Trigger |
|---|---|---|
| Resume Parser | `agents/resume_parser.py` | Resume upload (Tesseract OCR + LLM) |
| Eligibility Verifier | `agents/eligibility_verifier.py` | Eligibility check button |
| Background Verification | `agents/background_verification.py` | Shortlist (neutral facts) |
| Interview Co-pilot | `agents/interview_copilot.py` | Interview scheduling |
| Roster Compliance | `agents/roster_compliance.py` | Offer release |
| Duplicate Detection | `agents/duplicate_detection.py` | New application (signal) |

**Enable DeepSeek LLM:** edit `.env` →
```
LLM_PROVIDER=deepseek
LLM_API_BASE=https://api.deepseek.com/v1
LLM_API_KEY=your-key-here
LLM_MODEL=deepseek-chat
```

---

## 5. Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 6 + Django REST Framework |
| Multi-tenancy | django-tenants (schema-per-tenant, PostgreSQL) |
| Database | PostgreSQL 16 (required) |
| Frontend | Django templates + Bootstrap 5 + HTMX + Alpine.js |
| OCR | pytesseract + Tesseract (local; install separately) |
| LLM | OpenAI-compatible client (DeepSeek default, swappable) |
| i18n | English + Hindi (65 strings compiled) |

---

## 6. Commands

Run management commands inside the NEEPCO tenant:

```powershell
# Full data rebuild (all phases)
python manage.py tenant_command simulate_all --schema=neepco

# Individual simulations
python manage.py tenant_command simulate_neepco_advt        --schema=neepco   # Phase I recruitment
python manage.py tenant_command simulate_roster_panel       --schema=neepco   # roster + panels
python manage.py tenant_command simulate_duplicates_consents --schema=neepco  # dup + consents
python manage.py tenant_command simulate_internal_posting   --schema=neepco   # internal postings
python manage.py tenant_command simulate_workforce_planning --schema=neepco   # Phase II
python manage.py tenant_command simulate_talent_data        --schema=neepco   # Phase III

# Start dev server
python manage.py runserver 127.0.0.1:8000
```

---

## 7. Important Config Notes

- **Domain routing:** public = `localhost`, NEEPCO = `neepco.localhost` (hosts file entry added).
- **LLM key** lives only in `.env` (git-ignored). Never paste API keys in chat/code.
- **DigiLocker** is mocked (`DIGILOCKER_MOCK=True`). Flip to `False` when real credentials are ready.
- **Tesseract** must be installed for resume OCR; until then resume parsing reports `failed`.
- **Time zone:** `Asia/Kolkata`.

---

## 8. Demo Data Snapshot (NEEPCO)

| Data | Count |
|---|---|
| Advertisements | 1 (NEEPCO/02/2026) |
| Posts | 12 |
| Applications | ~105 |
| Duplicate flags | ~30 |
| Roster matrix rows | 60 |
| Panel entries | 38 |
| Consents | ~7 |
| Retirement forecast | 7 years |
| Recruitment batches | 3 |
| Skills | 12 |
| Training needs | 5 |

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `No tenant for hostname "127.0.0.1"` | Use `neepco.localhost` or `localhost`, not the IP |
| Logout "does nothing" | Uses POST form (Django 6 requirement) — works in browser |
| 500 on roster | Ensure `RosterMatrix` rows exist (run `simulate_roster_panel`) |
| Resume parse fails | Install Tesseract + set `TESSDATA_PREFIX` |
| Port 8000 busy | Kill stale python: `Get-Process python \| Stop-Process -Force` |

---

*Generated for the TalentFlow AI project. Version 3.0.*
