# Eligibility Engine — Structured Criteria + Real Verification (Phase 2.3)

**Date**: 2026-08-08
**Status**: Approved design (Wave 1 of remaining roadmap) — awaiting implementation plan
**Source**: `docs/specs/2026-08-08-production-grade-roadmap.md` §2.3

---

## 1. Problem

`agents/eligibility_verifier.py` today:
- Checks age against `advt.closing_date` (wrong — govt ads use a separate age-cut-off date).
- Returns `{"ok": None, "detail": "Required: <free text>. Manual review pending."}` for **every** qualification — the screening engine doesn't screen.
- Has no education / experience / certificate checks, no per-field verdicts beyond age, no human override, no audit.

`Post` has only free-text `qualification` / `experience_required` plus `max_age` and `required_certificates` (JSON).

## 2. Goal

Rule-based eligibility screening with per-field verdicts, a three-tier overall verdict (Eligible / Not Eligible / Manual Review), a human override with **mandatory reason** (audited), and a color-coded UI. Never auto-rejects silently — always human-reviewable (existing philosophy preserved).

## 3. Model changes (recruitment app, tenant schema) — migration `0011`

On `Post`:
- `min_education_level` — CharField(20, choices, blank=True): `x` (X / SSC), `xii` (XII / HSC), `diploma` (Diploma), `graduate` (Graduate/UG), `pg` (Post-graduate), `phd` (PhD).
- `min_percentage` — DecimalField(max_digits=5, decimal_places=2, null=True, blank=True).
- `experience_years` — PositiveIntegerField(null=True, blank=True).
- `age_cutoff_date` — DateField(null=True, blank=True).

New model `EligibilityOverride`:
```python
class EligibilityOverride(models.Model):
    application = models.OneToOneField("Application", on_delete=models.CASCADE, related_name="eligibility_override")
    verdict = models.BooleanField(help_text="Overridden overall verdict (True = eligible).")
    reason = models.TextField(help_text="Mandatory justification for the override.")
    overridden_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
```

## 4. Engine rewrite (`agents/eligibility_verifier.py`)

Keep the public entry point signature compatible (views already call it):
`verify_application(application, dob=None, digilocker_consent=None, cutoff=None) -> dict`.

**Data sources**: candidate DOB (`dob` arg or `application.candidate.date_of_birth`), `CandidateProfile` + `AcademicRecord` + `WorkExperience` (via `application.candidate`), `Document` rows (required-certificate presence), `DigiLocker` mock (existing).

**Per-field verdicts** — every flag is `{"ok": True | False | None, "detail": str}`:
- `age`: age on `cutoff or post.age_cutoff_date or advt.closing_date` vs `post.max_age`. No DOB → `ok=None`. No max_age → `ok=True` ("No maximum age constraint defined.").
- `education`: rank table — AcademicRecord levels `10th=1, 12th=2, diploma=2, ug=3, pg=4, other=3`; Post levels `x=1, xii=2, diploma=2, graduate=3, pg=4, phd=5`. Best academic record rank >= required rank → True. Documented limitation: AcademicRecord has no `phd` level, so a PhD-only record (stored `other`) cannot satisfy a `phd` requirement (candidates with PhDs hold PG records too). No records → `ok=None` ("No academic records available.").
- `percentage`: from the best relevant academic record vs `min_percentage`. CGPA→% conversion: `cgpa × 9.5` (documented in code comment). Marking type `cgpa` converted, `grade` → `ok=None` (cannot judge), `percentage` direct. `min_percentage` null → True.
- `experience`: total years from `WorkExperience` start/end (current = today), rounded, vs `post.experience_years`. None required → True.
- `certificates`: each entry in `post.required_certificates` must have a matching `Document` (`doc_type` contains the entry, case-insensitive). Missing → False with detail naming the missing certificate. Empty list → True.
- `category`: informational note — candidate `profile.category` vs `post.category_breakup`; fee-exemption note only (`ok` always True unless contradictory data).
- `digilocker`: unchanged behavior (mock fetch when consent given).

**Overall verdict**: any flag `ok is False` → `eligible=False, verdict="not_eligible"`; else any `ok is None` → `eligible=None, verdict="manual_review"`; else `eligible=True, verdict="eligible"`.

**Return dict**:
```python
{
    "application_id": ..., "post": post.name, "post_code": post.post_code,
    "cutoff": cutoff, "flags": {...}, "eligible": bool|None,
    "verdict": "eligible" | "not_eligible" | "manual_review",
    "checked_at": isoformat,
}
```

## 5. Human override + audit

- View: `run_eligibility` (already recruiter-gated) — POST with `override_verdict` (on/off) + `override_reason`. Reason must be non-empty (`EligibilityOverride.reason` blank → ValidationError shown in UI; never silently saved).
- On create: `EligibilityOverride` row + `log_audit(actor=request.user, application, field_name="eligibility_override", old_value=current verdict, new_value=override verdict, reason=override_reason)`.
- Overridden applications render the override verdict card (amber "Overridden" chip) with the reason + who/when.
- Updating an existing override = `update_or_create` + audit with old/new.

## 6. UI

`templates/recruitment/eligibility_result.html` rewritten:
- Verdict card color-coded: green (`--tf-success`) Eligible, red (`--tf-danger`) Not Eligible, amber (`--tf-warning`) Manual Review + Overridden chip when an override exists.
- Per-field rows with `ok` icon (✓ / ✗ / ?), `detail` text — expandable `<details>`/`<summary>` or always-visible list (prefer always-visible; small field count).
- Override form (POST): checkbox `override_verdict` + textarea `override_reason` (required); shows current override when present with reason/actor/timestamp.
- Existing `run_eligibility` GET flow unchanged (verdict dict → template).

## 7. Error handling

- `verify_application` never raises on missing profile/academic/work data (each field degrades to `ok=None` with an explanatory detail).
- Malformed DOB/cutoff strings: existing `_age_on_cutoff` coercion reused (returns None → `ok=None`).
- Override reason blank → form-level ValidationError, 200 re-render with error message (no 500).

## 8. Testing (`agents/test_eligibility.py` + app tests)

| Test | Asserts |
|---|---|
| age vs age_cutoff_date | cutoff arg wins; post.age_cutoff_date beats advt.closing_date; legacy fallback = closing_date |
| education rank | ug meets graduate; 10th fails graduate; no records → None |
| percentage | percentage record meets/under min; cgpa × 9.5 conversion; grade → None |
| experience | summed years meets/under requirement |
| certificates | missing required cert → False + named detail |
| overall tiers | one False → not_eligible; None-only → manual_review; all True → eligible |
| override | reason required (blank rejected); creates EligibilityOverride + AuditEvent with actor |

## 9. Commands after implementation

1. `manage.py makemigrations recruitment` (0011) + `manage.py migrate_schemas`
2. `pytest -q` full suite
3. Live E2E (recruiter runs eligibility on a real application; override flow)

## 10. Commit format

`Phase 2: Eligibility — <brief>`
