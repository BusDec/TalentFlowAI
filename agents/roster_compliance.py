"""Roster Compliance Agent.

Validates that an offer/joining consumes a valid category slot against the post's
RosterMatrix. Warns (never auto-blocks) on roster breach and logs the decision.
"""

import datetime


def validate_offer(application, category, allocate_slot=False):
    """Validate category slot availability for an application.

    Args:
        application: recruitment.Application
        category: one of ur/obc/sc/st/ews (or pwbd for horizontal)
        allocate_slot: if True, mark the matching allocation as fills_slot

    Returns a dict with status, warning, and roster details.
    """
    post = application.post
    matrix_rows = list(post.roster_matrix.filter(category=category))
    if not matrix_rows:
        return {
            "status": "no_matrix",
            "warning": f"No roster matrix row for category '{category}' on {post.name}. "
                       "Manual verification required.",
            "category": category,
            "checked_at": datetime.datetime.now().isoformat(),
        }

    # PwBD horizontal capacity is tracked on each category row; sum them.
    rows_for_horizontal = (
        post.roster_matrix.all() if category == "pwbd" else matrix_rows
    )
    for row in rows_for_horizontal:
        filled = row.filled_count
        total = row.total_vacancies
        warning = row.breach_warning
        if row.category == category and allocate_slot and not row.is_full:
            row.allocations.filter(application=application, category=category).update(
                fills_slot=True, is_verified=True, verified_at=datetime.datetime.now()
            )
        return {
            "status": "ok" if not warning else "breach",
            "warning": warning or "Slot available.",
            "category": category,
            "filled": filled,
            "total": total,
            "checked_at": datetime.datetime.now().isoformat(),
        }

    return {
        "status": "ok",
        "warning": "No applicable roster rows.",
        "category": category,
        "checked_at": datetime.datetime.now().isoformat(),
    }
