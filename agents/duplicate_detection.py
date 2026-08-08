"""Duplicate Detection Agent.

Fuzzy-matches a new application against existing applications across ALL
advertisements using normalised name + DOB + email + phone. Raises DuplicateFlag
records for human resolution — never auto-rejects.
"""

import re

from recruitment.models import Candidate, DuplicateFlag


def _norm_name(value):
    if not value:
        return ""
    return re.sub(r"[^a-z]", "", "".join(value.split()).lower())


def _norm(value):
    return re.sub(r"[\s\-()+.]+", "", (value or "")).lower()


def _jaccard(a, b):
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    set_a, set_b = set(a), set(b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _score(existing_candidate, new_candidate):
    """Return (confidence, matched_fields) 0-100."""
    scores = []
    fields = []

    if _norm_name(new_candidate.first_name) and _norm_name(existing_candidate.first_name):
        s = _jaccard(
            _norm_name(new_candidate.first_name),
            _norm_name(existing_candidate.first_name),
        )
        if s > 0.6:
            scores.append(s * 40)
            fields.append("first_name")

    if new_candidate.email and existing_candidate.email:
        if _norm(new_candidate.email) == _norm(existing_candidate.email):
            scores.append(30)
            fields.append("email")

    if new_candidate.mobile and existing_candidate.mobile:
        if _norm(new_candidate.mobile) == _norm(existing_candidate.mobile):
            scores.append(20)
            fields.append("mobile")

    if new_candidate.date_of_birth and existing_candidate.date_of_birth:
        if new_candidate.date_of_birth == existing_candidate.date_of_birth:
            scores.append(10)
            fields.append("date_of_birth")

    if not scores:
        return 0, []

    confidence = min(100, int(sum(scores)))
    return confidence, fields


def detect_duplicates(new_application, threshold=50):
    """Scan for existing applications matching the new one.

    Returns a list of (existing_application, confidence, matched_fields).
    """
    new_candidate = new_application.candidate
    matches = []

    existing_applications = (
        Candidate.objects
        .exclude(applications__id=new_application.id)
        .filter(applications__isnull=False)
        .distinct()
    )

    for cand in existing_applications:
        confidence, fields = _score(cand, new_candidate)
        if confidence >= threshold and fields:
            for app in cand.applications.all():
                matches.append((app, confidence, fields))

    return matches


def flag_duplicates(new_application, threshold=50):
    """Create DuplicateFlag records for detected matches (pending resolution)."""
    created_flags = []
    for existing_app, confidence, fields in detect_duplicates(new_application, threshold):
        # avoid re-flagging the same pair
        if DuplicateFlag.objects.filter(
            application_a=new_application, application_b=existing_app
        ).exists() or DuplicateFlag.objects.filter(
            application_a=existing_app, application_b=new_application
        ).exists():
            continue
        flag = DuplicateFlag.objects.create(
            candidate=new_application.candidate,
            application_a=new_application,
            application_b=existing_app,
            confidence=confidence,
            match_fields=fields,
            resolution="pending",
        )
        created_flags.append(flag)
    return created_flags
