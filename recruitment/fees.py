"""Fee exemption engine — §3.3 of Phase 3 design.

Pure functions determining whether a candidate is exempt from application fee
and what the standard fee amount is.

Exemption rules (DoPT / Government of India recruitment norms):
    1. SC / ST / OBC / EWS candidates → exempt
    2. Female candidates (all categories) → exempt
    3. PwBD (Persons with Benchmark Disabilities) → exempt
    4. UR male without PwBD → NOT exempt
"""

from decimal import Decimal

# Reserved categories that qualify for fee exemption.
_EXEMPT_CATEGORIES = frozenset({"sc", "st", "obc", "ews"})

# Default application fee (₹500).
DEFAULT_FEE = Decimal("500.00")


def fee_amount(post) -> Decimal:
    """Return the application fee for *post*.

    Currently returns the standard ₹500.  Accepts ``post`` for interface
    stability; a future iteration may read a per-post override.
    """
    return DEFAULT_FEE


def fee_exempt(candidate, post) -> tuple[bool, str]:
    """Determine whether *candidate* is exempt from the fee for *post*.

    Returns ``(is_exempt, reason)``.  The reason is a human-readable string
    suitable for display on the payment page and for storage in
    ``Payment.exempt_reason``.

    Exemption checks are evaluated in priority order:
        1. SC / ST / OBC / EWS category
        2. Female gender
        3. PwBD (Persons with Benchmark Disabilities)

    If none match, the candidate is not exempt.
    """
    # Import here to avoid circular imports at module level.
    from profiles.models import CandidateProfile

    try:
        profile = candidate.profile
    except CandidateProfile.DoesNotExist:
        # No profile → cannot determine exemption → not exempt.
        return False, "No profile on file — no exemption applicable."

    category = (profile.category or "").strip().lower()
    gender = (profile.gender or "").strip().upper()
    is_pwbd = profile.is_pwbd

    # 1. Reserved category
    if category in _EXEMPT_CATEGORIES:
        return True, f"{category.upper()} category — exempt per DoPT guidelines."

    # 2. Female candidates
    if gender == "F":
        return True, "Female candidate — exempt per Government of India recruitment norms."

    # 3. PwBD
    if is_pwbd:
        return True, "PwBD — exempt per Section 34 of the RPwD Act, 2016."

    # No exemption
    return False, "No exemption applicable — full fee payable."
