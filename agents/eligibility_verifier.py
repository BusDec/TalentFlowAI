"""Eligibility & Document Verification Agent.

Combines OCR-extracted document data and (mock) DigiLocker results, then applies
rule-based eligibility checks from the Post definition. Produces per-field flags
and an overall verdict. Always human-reviewable; never auto-rejects silently.
"""

import datetime

from recruitment.digilocker.client import fetch_documents, verify_signature


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


def verify_application(application, dob=None, digilocker_consent=None, cutoff=None):
    """Return an eligibility verdict dict for an application.

    Args:
        application: recruitment.Application instance (has .post, .candidate)
        dob: candidate date of birth (date or ISO string)
        digilocker_consent: a consent reference string, or None to skip DL fetch
        cutoff: eligibility cut-off date (defaults to post.advertisement.closing_date)
    """
    post = application.post
    advt = post.advertisement
    cutoff = cutoff or advt.closing_date

    flags = {}
    # --- Age check ----------------------------------------------------------
    age = _age_on_cutoff(dob, cutoff) if dob else None
    if post.max_age is not None:
        if age is not None:
            flags["age"] = {
                "ok": age <= post.max_age,
                "value": age,
                "max": post.max_age,
                "detail": f"Age {age} on {cutoff} (max {post.max_age}).",
            }
        else:
            flags["age"] = {"ok": None, "detail": "Date of birth not available for age check."}
    else:
        flags["age"] = {"ok": True, "detail": "No maximum age constraint defined."}

    # --- Qualification placeholder ------------------------------------------
    flags["qualification"] = {"ok": None, "detail": f"Required: {post.qualification}. Manual review pending."}

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

    overall_ok = all(
        f.get("ok") is not False for f in flags.values() if isinstance(f, dict) and "ok" in f
    )
    return {
        "application_id": application.application_id,
        "post": post.name,
        "cutoff": str(cutoff),
        "flags": flags,
        "eligible": overall_ok,
        "verdict": "Proceed" if overall_ok else "Review required",
        "checked_at": datetime.datetime.now().isoformat(),
    }
