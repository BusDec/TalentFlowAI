"""Fairness analysis engine.

Pure functions for adverse-impact analysis (EEOC 4/5ths rule) and statistical
parity computation.  No Django ORM imports — callers pass plain dicts so these
functions stay unit-testable without a database.
"""

import re


# ── Adverse Impact (4/5ths rule) ────────────────────────────────────────────


def compute_adverse_impact(selection_rates_by_category: dict) -> dict:
    """Apply the EEOC 4/5ths (80 %) rule to category selection rates.

    Parameters
    ----------
    selection_rates_by_category : dict[str, float]
        ``{category_code: selection_rate}`` where *selection_rate* is a
        fraction in [0, 1] (e.g. 0.40 = 40 %).

    Returns
    -------
    dict with keys:
        * ``threshold``      — 80 % of the highest rate (float)
        * ``max_rate``        — highest selection rate across all categories
        * ``categories``      — per-category detail list
        * ``flagged``         — list of category codes below the threshold
        * ``has_adverse_impact`` — bool, True when *flagged* is non-empty
    """
    if not selection_rates_by_category:
        return {
            "threshold": 0.0,
            "max_rate": 0.0,
            "categories": [],
            "flagged": [],
            "has_adverse_impact": False,
        }

    max_rate = max(selection_rates_by_category.values())
    threshold = max_rate * 0.8

    categories = []
    flagged = []
    for cat, rate in sorted(selection_rates_by_category.items()):
        below = rate < threshold
        detail = {
            "category": cat,
            "rate": rate,
            "ratio_to_max": rate / max_rate if max_rate else 0.0,
            "below_threshold": below,
        }
        categories.append(detail)
        if below:
            flagged.append(cat)

    return {
        "threshold": threshold,
        "max_rate": max_rate,
        "categories": categories,
        "flagged": flagged,
        "has_adverse_impact": bool(flagged),
    }


# ── Statistical Parity ──────────────────────────────────────────────────────


def compute_statistical_parity(selection_rates: dict) -> dict:
    """Compute statistical-parity metrics for a set of category selection rates.

    Parameters
    ----------
    selection_rates : dict[str, float]
        ``{category_code: selection_rate}`` (fraction in [0, 1]).

    Returns
    -------
    dict with keys:
        * ``overall_rate``     — mean selection rate across all categories
        * ``categories``       — per-category detail (rate + deviation from mean)
        * ``max_disparity``    — max absolute deviation from the overall rate
        * ``min_rate`` / ``max_rate`` — extremes
    """
    if not selection_rates:
        return {
            "overall_rate": 0.0,
            "categories": [],
            "max_disparity": 0.0,
            "min_rate": 0.0,
            "max_rate": 0.0,
        }

    rates = list(selection_rates.values())
    overall = sum(rates) / len(rates)

    categories = []
    for cat, rate in sorted(selection_rates.items()):
        categories.append({
            "category": cat,
            "rate": rate,
            "deviation": rate - overall,
        })

    deviations = [abs(c["deviation"]) for c in categories]

    return {
        "overall_rate": overall,
        "categories": categories,
        "max_disparity": max(deviations) if deviations else 0.0,
        "min_rate": min(rates),
        "max_rate": max(rates),
    }


# ── Prompt Sanitisation (demographic stripping) ─────────────────────────────

# Fields that reveal protected demographic characteristics and MUST NOT be
# forwarded to an LLM evaluator so scores cannot be biased by identity.
_DEMOGRAPHIC_KEYS = frozenset({
    "name", "first_name", "last_name", "full_name",
    "gender", "sex",
    "date_of_birth", "dob", "birth_date", "age",
    "caste", "category", "religion", "nationality", "marital_status",
    "photo", "photograph", "image", "avatar",
    "father_name", "mother_name", "spouse_name", "parent_name",
    "address", "street", "city", "state", "pincode", "zip_code",
    "phone", "mobile", "email",
    "aadhaar", "aadhaar_number", "pan", "pan_number",
})


def sanitize_resume_for_prompt(resume: dict) -> dict:
    """Strip demographic/identity fields from a parsed resume dict.

    Returns a *new* dict with demographic keys removed.  Nested dicts are
    recursed into; lists of dicts are recursed element-wise.  The original
    ``resume`` is never mutated.
    """
    if not isinstance(resume, dict):
        return resume

    clean = {}
    for key, value in resume.items():
        if key.lower().strip() in _DEMOGRAPHIC_KEYS:
            continue
        if isinstance(value, dict):
            clean[key] = sanitize_resume_for_prompt(value)
        elif isinstance(value, list):
            clean[key] = [
                sanitize_resume_for_prompt(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            clean[key] = value
    return clean
