# Eligibility Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder eligibility check with rule-based per-field screening (age/education/percentage/experience/certificates), a three-tier overall verdict, and an audited human override.

**Architecture:** Four new `Post` fields + `EligibilityOverride` model (migration 0011); `agents/eligibility_verifier.py` rewritten around a `_check_*` family returning `{ok, detail}` per field; `run_eligibility` view gains an override POST; `eligibility_result.html` color-coded.

**Tech Stack:** Django 6.0, django-tenants, PostgreSQL 16, pytest (57 existing tests).

## Global Constraints

- All new models tenant-schema (recruitment). Run `manage.py migrate_schemas` after model changes — never plain `migrate`.
- Never auto-reject silently: every `False` verdict must carry a human-readable `detail`; the engine never writes status changes.
- `verify_application(application, dob=None, digilocker_consent=None, cutoff=None)` signature must stay compatible (views + existing tests call it).
- Override reason is mandatory; creating/updating an override writes an AuditEvent.
- Python: `.venv/Scripts/python.exe`; tests: targeted pytest; commit format `Phase 2: Eligibility — <brief>`.

---

### Task 1: Post fields + EligibilityOverride model + migration 0011

**Files:** `recruitment/models.py`, `recruitment/migrations/0011_*.py` (generated), `recruitment/test_eligibility.py` (create)

**Interfaces:** Produces `Post.min_education_level` (choices x/xii/diploma/graduate/pg/phd, blank), `Post.min_percentage` (Decimal 5,2 null), `Post.experience_years` (PositiveInteger null), `Post.age_cutoff_date` (DateField null); `EligibilityOverride` (application OneToOne related_name="eligibility_override", verdict BooleanField, reason TextField, overridden_by FK settings.AUTH_USER_MODEL null SET_NULL, created_at auto). Consumed by Task 2+.

- [ ] **Step 1: Failing test** — `recruitment/test_eligibility.py`:
```python
def test_post_has_structured_criteria(tenant, advertisement):
    from recruitment.models import Post
    post = advertisement.posts.first()
    assert hasattr(post, "min_education_level")
    assert hasattr(post, "min_percentage")
    assert hasattr(post, "experience_years")
    assert hasattr(post, "age_cutoff_date")

def test_eligibility_override_model(tenant, application):
    from accounts.models import User
    from recruitment.models import EligibilityOverride
    user = User.objects.create_user(username="ovr", password="x")
    o = EligibilityOverride.objects.create(application=application, verdict=True, reason="doc verified", overridden_by=user)
    assert o.reason == "doc verified"
    assert application.eligibility_override.pk == o.pk
```
- [ ] **Step 2: Run** — expect FAIL (fields/models missing). `.venv/Scripts/python.exe -m pytest recruitment/test_eligibility.py -q`
- [ ] **Step 3: Implement** — add the 4 fields to `Post` and the `EligibilityOverride` model at the bottom of `recruitment/models.py`. Generate migration: `.venv/Scripts/python.exe manage.py makemigrations recruitment` → `0011_*.py` (do not apply to dev DB).
- [ ] **Step 4: Run tests** — expect PASS (2 passed).
- [ ] **Step 5: Commit** — `Phase 2: Eligibility — Post criteria fields + EligibilityOverride model (migration 0011)`

### Task 2: Engine rewrite — check helpers + overall verdict

**Files:** `agents/eligibility_verifier.py` (rewrite), `recruitment/test_eligibility.py` (append)

**Interfaces:** Consumes Post fields (Task 1), CandidateProfile/AcademicRecord/WorkExperience/Document via `application.candidate`. Produces `verify_application(...)` returning `{application_id, post, post_code, cutoff, flags, eligible, verdict, checked_at}`; `eligible` in {True, False, None}; `verdict` in {"eligible","not_eligible","manual_review"}.

- [ ] **Step 1: Failing tests** (append):
```python
def test_engine_verdict_tiers(tenant, application):
    from agents.eligibility_verifier import verify_application
    v = verify_application(application)
    assert v["verdict"] in ("eligible", "not_eligible", "manual_review")
    assert set(v) >= {"application_id", "post", "flags", "eligible", "verdict"}
    for f in ("age", "education", "experience", "certificates"):
        assert f in v["flags"] and "ok" in v["flags"][f] and "detail" in v["flags"][f]

def test_age_uses_cutoff_arg(tenant, application):
    from agents.eligibility_verifier import verify_application
    application.candidate.date_of_birth = "1995-06-15"
    application.candidate.save()
    v = verify_application(application, cutoff="2026-01-01")
    assert v["cutoff"] == "2026-01-01" or str(v["cutoff"]).startswith("2026-01-01")

def test_missing_required_certificate_false(tenant, application):
    from agents.eligibility_verifier import verify_application
    application.post.required_certificates = ["GATE scorecard"]
    application.post.save()
    v = verify_application(application)
    assert v["flags"]["certificates"]["ok"] is False
    assert "GATE scorecard" in v["flags"]["certificates"]["detail"]
```
- [ ] **Step 2: Run** — expect FAIL (current engine has no education/experience/certificates flags; certificate check absent).
- [ ] **Step 3: Implement** — rewrite `agents/eligibility_verifier.py`:
  - Keep `_age_on_cutoff` and `_percentage_ok` (coerce str/date/datetime as today).
  - Add `_EDUCATION_RANK = {"10th": 1, "12th": 2, "diploma": 2, "ug": 3, "pg": 4, "other": 3}` and `_POST_LEVEL_RANK = {"x": 1, "xii": 2, "diploma": 2, "graduate": 3, "pg": 4, "phd": 5}`; `_level_ok(level)` helper; CGPA→% = `float(cgpa) * 9.5` (comment).
  - `_check_age(post, dob, cutoff)` → `{ok, detail}` (None-dob → ok=None; no max_age → True).
  - `_check_education(candidate, post)` → best AcademicRecord rank vs `post.min_education_level`; no records → None.
  - `_check_percentage(candidate, post)` → best relevant record; cgpa conversion; grade → None; null min → True.
  - `_check_experience(candidate, post)` → sum WorkExperience years (end None → today), round; null → True.
  - `_check_certificates(application, post)` → every `required_certificates` entry matched by a Document doc_type (case-insensitive contains); missing → False + detail.
  - `_check_category(profile, post)` → informational note, ok=True.
  - `verify_application` assembles flags (age, education, percentage, experience, certificates, category, digilocker unchanged) and computes overall per spec §4. `checked_at` = `datetime.datetime.now().isoformat()`.
- [ ] **Step 4: Run tests** — expect PASS (all new + existing eligibility tests).
- [ ] **Step 5: Commit** — `Phase 2: Eligibility — engine rewrite with per-field verdicts and 3-tier overall`

### Task 3: Override flow in view + audit

**Files:** `recruitment/views.py` (run_eligibility), `recruitment/test_eligibility.py` (append)

**Interfaces:** Consumes `EligibilityOverride` (Task 1) and `log_audit` (exists). Produces: `run_eligibility` handles POST with `override_verdict` + `override_reason`; invalid reason → 200 re-render with error; valid → update_or_create + audit → redirect to `run_eligibility`.

- [ ] **Step 1: Failing test**:
```python
def test_override_requires_reason(api_client, tenant, application, recruiter_user):
    api_client.force_login(recruiter_user)
    r = api_client.post(f"/applications/{application.application_id}/eligibility/", {"override_verdict": "on", "override_reason": ""})
    assert r.status_code == 200  # re-render with error, not 302
    from recruitment.models import EligibilityOverride
    assert not EligibilityOverride.objects.filter(application=application).exists()

def test_override_writes_audit(api_client, tenant, application, recruiter_user):
    api_client.force_login(recruiter_user)
    r = api_client.post(f"/applications/{application.application_id}/eligibility/", {"override_verdict": "on", "override_reason": "documents verified"})
    assert r.status_code == 302
    from recruitment.models import AuditEvent, EligibilityOverride
    o = EligibilityOverride.objects.get(application=application)
    assert o.verdict is True and o.overridden_by == recruiter_user
    assert AuditEvent.objects.filter(application=application, field_name="eligibility_override").exists()
```
- [ ] **Step 2: Run** — expect FAIL (view has no POST handling).
- [ ] **Step 3: Implement** — in `run_eligibility`: on POST, read `override_verdict` ("on"/"1"/"true") + `override_reason`. If reason blank → render with `{"override_error": "Reason is required."}` (200). Else `EligibilityOverride.objects.update_or_create(application=application, defaults={"verdict": verdict, "reason": reason, "overridden_by": request.user})`; `log_audit(request.user, application, "eligibility_override", previous_verdict_str, new_verdict_str, reason=reason)`; messages.success; redirect to the eligibility URL. GET path passes `override` into context.
- [ ] **Step 4: Run tests** — expect PASS.
- [ ] **Step 5: Commit** — `Phase 2: Eligibility — audited human override in run_eligibility`

### Task 4: Verdict UI

**Files:** `templates/recruitment/eligibility_result.html` (rewrite), `recruitment/test_eligibility.py` (append)

- [ ] **Step 1: Failing test**:
```python
def test_eligibility_page_renders_verdict_card(api_client, tenant, application, recruiter_user):
    api_client.force_login(recruiter_user)
    r = api_client.get(f"/applications/{application.application_id}/eligibility/")
    assert r.status_code == 200
    body = r.content.decode()
    assert "verdict" in body.lower() or "eligible" in body.lower()
```
- [ ] **Step 2: Run** — expect PASS already (page exists) — keep as smoke; the real assertion is Task 4's visual contract (verdict card + per-field rows + override form), verified manually + this smoke.
- [ ] **Step 3: Implement** — rewrite `eligibility_result.html`: verdict card (class `tf-alert success|warning|danger` mapped from verdict); per-field table with ok icon + detail; override form (POST to same URL) with `override_verdict` checkbox + `override_reason` textarea; when `override` exists show amber "Overridden" chip + reason/actor/created_at; `override_error` shown when present. Context keys: `verdict` (dict), `override` (EligibilityOverride or None), `override_error` (str|None).
- [ ] **Step 4: Run tests** — expect PASS (smoke + prior).
- [ ] **Step 5: Commit** — `Phase 2: Eligibility — color-coded verdict card UI with override form`

### Task 5: Final verification

- [ ] `manage.py migrate_schemas` (applies 0011 to both schemas) — expect clean.
- [ ] `pytest -q` — expect 60+ passed (57 + new).
- [ ] `manage.py makemigrations --check --dry-run` — "No changes detected".
- [ ] Live E2E: start server 8123 + `python e2e_smoke.py` — expect green (eligibility GET/POST already in the E2E route table; the POST now needs no form data to succeed for recruiter — it renders 200 as before).
- [ ] Commit any verification fixes.
