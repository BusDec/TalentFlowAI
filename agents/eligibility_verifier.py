"""Eligibility & Document Verification Agent.

Combines OCR-extracted document data and (mock) DigiLocker results, then applies
rule-based eligibility checks from the Post definition. Produces per-field flags
and a three-tier overall verdict (eligible / not_eligible / manual_review).
Always human-reviewable; never auto-rejects silently.
"""

import datetime

from recruitment.digilocker.client import fetch_documents, verify_signature


# Rank tables mapping academic record levels and Post minimum education levels
# onto a comparable 1-5 scale. "other" is deliberately ranked at UG level (3):
# a PhD-only record stored as "other" cannot satisfy a "phd" requirement
# (candidates with PhDs hold PG records too). Documented limitation.
_EDUCATION_RANK = {"10th": 1, "12th": 2, "diploma": 2, "ug": 3, "pg": 4, "other": 3}

_POST_LEVEL_RANK = {"x": 1, "xii": 2, "diploma": 2, "graduate": 3, "pg": 4, "phd": 5}


def _age_on_cutoff(dob, cutoff):
    """Return age in completed years as of cutoff date."""
    if not dob or not cutoff:
        return None
    if isinstance(dob, str):
        try:
            dob = datetime.date.fromisoformat(dob)
        except ValueError:
            return None
    if isinstance(cutoff, str):
        try:
            cutoff = datetime.date.fromisoformat(cutoff)
        except ValueError:
            return None
    if isinstance(dob, datetime.datetime):
        dob = dob.date()
    if isinstance(cutoff, datetime.datetime):
        cutoff = cutoff.date()
    return cutoff.year - dob.year - ((cutoff.month, cutoff.day) < (dob.month, dob.day))


def _percentage_ok(percentage, required_min):
    if required_min is None:
        return True
    try:
        return float(percentage) >= float(required_min)
    except (TypeError, ValueError):
        return None


def _level_ok(level):
    """Rank of an AcademicRecord level on the education scale, or None."""
    return _EDUCATION_RANK.get(level)


def _record_percentage(record):
    """Convert an AcademicRecord score to a percentage, or None if not comparable.

    CGPA → % uses the standard Indian board conversion: cgpa × 9.5.
    Grade-only (or unknown marking) scores cannot be judged objectively.
    """
    if not record.score:
        return None
    if record.marking_type == "percentage":
        try:
            return float(record.score)
        except (TypeError, ValueError):
            return None
    if record.marking_type == "cgpa":
        try:
            # CGPA→% conversion: multiply by 9.5.
            return float(record.score) * 9.5
        except (TypeError, ValueError):
            return None
    return None  # grade or unknown marking type


def _check_age(post, dob, cutoff):
    """Age on cutoff vs post.max_age. {ok, detail} — None dob → ok=None."""
    if post.max_age is None:
        return {"ok": True, "detail": "No maximum age constraint defined."}
    age = _age_on_cutoff(dob, cutoff)
    if age is None:
        return {"ok": None, "detail": "Date of birth not available for age check."}
    return {
        "ok": age <= post.max_age,
        "value": age,
        "max": post.max_age,
        "detail": f"Age {age} on {cutoff} (max {post.max_age}).",
    }


def _check_education(candidate, post):
    """Best AcademicRecord rank vs post.min_education_level. {ok, detail}."""
    if not post.min_education_level:
        return {"ok": True, "detail": "No minimum education level required."}
    required = _POST_LEVEL_RANK.get(post.min_education_level)
    if required is None:
        return {
            "ok": None,
            "detail": f"Unknown required education level: {post.min_education_level}. Manual review pending.",
        }
    records = list(candidate.academic_records.all())
    if not records:
        return {"ok": None, "detail": "No academic records available."}
    ranks = [_level_ok(rec.level) for rec in records if _level_ok(rec.level) is not None]
    if not ranks:
        return {"ok": None, "detail": "Academic records have unrecognised levels; cannot rank education."}
    best = max(ranks)
    return {
        "ok": best >= required,
        "value": best,
        "required": required,
        "detail": f"Highest education rank {best} vs required rank {required} ({post.min_education_level}).",
    }


def _check_percentage(candidate, post):
    """Best relevant academic record score vs post.min_percentage. {ok, detail}."""
    if post.min_percentage is None:
        return {"ok": True, "detail": "No minimum percentage required."}
    records = list(candidate.academic_records.all())
    if not records:
        return {"ok": None, "detail": "No academic records available for percentage check."}
    best_pct, best_rec = None, None
    for rec in records:
        pct = _record_percentage(rec)
        if pct is not None and (best_pct is None or pct > best_pct):
            best_pct, best_rec = pct, rec
    if best_pct is None:
        return {
            "ok": None,
            "detail": "Academic scores are grade-only and cannot be compared to the minimum percentage.",
        }
    return {
        "ok": _percentage_ok(best_pct, post.min_percentage),
        "value": best_pct,
        "required": float(post.min_percentage),
        "detail": f"Best score {best_pct}% (from {best_rec.get_level_display()}) vs required {post.min_percentage}%.",
    }


def _check_experience(candidate, post):
    """Sum WorkExperience years (end None → today), rounded. {ok, detail}."""
    if post.experience_years is None:
        return {"ok": True, "detail": "No minimum experience required."}
    today = datetime.date.today()
    total_days, count = 0, 0
    for exp in candidate.work_experiences.all():
        if not exp.start_date:
            continue
        end = exp.end_date or today
        total_days += max((end - exp.start_date).days, 0)
        count += 1
    if count == 0:
        return {"ok": None, "detail": "No work experience records with start dates available."}
    total_years = round(total_days / 365.25)
    return {
        "ok": total_years >= post.experience_years,
        "value": total_years,
        "required": post.experience_years,
        "detail": f"Total experience {total_years} years (from {count} record(s)) vs required {post.experience_years} years.",
    }


def _check_certificates(application, post):
    """Every required_certificates entry matched by a Document doc_type. {ok, detail}."""
    required = post.required_certificates or []
    if not required:
        return {"ok": True, "detail": "No certificates required."}
    doc_types = [doc.doc_type.lower() for doc in application.documents.all()]
    missing = [
        entry for entry in required if not any(entry.lower() in dt for dt in doc_types)
    ]
    if missing:
        return {
            "ok": False,
            "missing": missing,
            "detail": f"Missing required certificate(s): {', '.join(missing)}.",
        }
    return {"ok": True, "detail": "All required certificates present."}


def _check_category(profile, post):
    """Informational note on candidate category vs post roster — ok always True."""
    if profile is None:
        return {"ok": True, "detail": "No candidate profile category declared."}
    category = profile.category
    breakup = post.category_breakup or {}
    if not category:
        return {"ok": True, "detail": "No candidate category declared — informational only."}
    if category in breakup and breakup.get(category):
        detail = (
            f"Candidate category {category.upper()} has {breakup[category]} vacancy slot(s) "
            f"in this post."
        )
    elif breakup:
        detail = (
            f"Candidate category {category.upper()} is not in this post's category breakup "
            f"({', '.join(breakup)}); allocation requires manual review."
        )
    else:
        detail = f"Candidate category {category.upper()} declared; post defines no category breakup."
    return {"ok": True, "detail": detail, "category": category}


def verify_application(application, dob=None, digilocker_consent=None, cutoff=None):
    """Return an eligibility verdict dict for an application.

    Args:
        application: recruitment.Application instance (has .post, .candidate)
        dob: candidate date of birth (date or ISO string); falls back to
            application.candidate.date_of_birth when not provided
        digilocker_consent: a consent reference string, or None to skip DL fetch
        cutoff: eligibility cut-off date (defaults to post.age_cutoff_date or
            post.advertisement.closing_date)
    """
    post = application.post
    candidate = application.candidate
    cutoff = cutoff or post.age_cutoff_date or post.advertisement.closing_date
    dob = dob or candidate.date_of_birth
    profile = getattr(candidate, "profile", None)

    flags = {
        "age": _check_age(post, dob, cutoff),
        "education": _check_education(candidate, post),
        "percentage": _check_percentage(candidate, post),
        "experience": _check_experience(candidate, post),
        "certificates": _check_certificates(application, post),
        "category": _check_category(profile, post),
    }

    # --- DigiLocker document fetch (mock) ------------------------------------
    dl_flags = []
    if digilocker_consent:
        try:
            docs = fetch_documents(digilocker_consent, dob=dob)
            for doc in docs:
                valid = verify_signature(doc)
                dl_flags.append(
                    {
                        "doc_type": doc.doc_type,
                        "issuer": doc.issuer,
                        "issue_date": doc.issue_date,
                        "signature_valid": valid,
                        "data": doc.data,
                    }
                )
        except Exception as exc:  # pragma: no cover
            dl_flags = [{"error": str(exc)}]
    flags["digilocker"] = {"fetched": bool(digilocker_consent), "documents": dl_flags}

    # --- Overall verdict (3-tier) --------------------------------------------
    check_flags = [f for f in flags.values() if isinstance(f, dict) and "ok" in f]
    if any(f["ok"] is False for f in check_flags):
        eligible, verdict = False, "not_eligible"
    elif any(f["ok"] is None for f in check_flags):
        eligible, verdict = None, "manual_review"
    else:
        eligible, verdict = True, "eligible"

    return {
        "application_id": application.application_id,
        "post": post.name,
        "post_code": post.post_code,
        "cutoff": str(cutoff),
        "flags": flags,
        "eligible": eligible,
        "verdict": verdict,
        "checked_at": datetime.datetime.now().isoformat(),
    }
