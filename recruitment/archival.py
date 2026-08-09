"""Data archival helpers — eligibility detection + audit-event hash-chain.

Phase 4.10: archive_eligible() finds closed/terminal applications older than
one year; hash_row() / verify_chain() provide tamper-evident ordering of
AuditEvent rows using a SHA-256 hash-chain.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from typing import TYPE_CHECKING

from django.db.models import Q

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from recruitment.models import Application, AuditEvent

# Application statuses considered terminal / archivable.
TERMINAL_STATUSES = ("joined", "rejected", "withdrawn")

# How old the advertisement closing_date must be (relative to today).
_ARCHIVE_THRESHOLD_YEARS = 1


def archive_eligible() -> "QuerySet[Application]":
    """Return applications eligible for archival.

    An application is eligible when:
    * its status is one of ``TERMINAL_STATUSES``, **and**
    * the parent advertisement's ``closing_date`` is more than one year ago.
    """
    from recruitment.models import Application

    cutoff = date.today() - timedelta(days=365 * _ARCHIVE_THRESHOLD_YEARS)
    return Application.objects.filter(
        status__in=TERMINAL_STATUSES,
        post__advertisement__closing_date__lt=cutoff,
    )


# ---------------------------------------------------------------------------
# Hash-chain helpers
# ---------------------------------------------------------------------------

def _event_canonical(event: "AuditEvent") -> str:
    """Produce a deterministic string representation of an audit event."""
    return "|".join(
        str(v)
        for v in (
            event.pk,
            event.timestamp.isoformat() if event.timestamp else "",
            event.actor_id or "",
            event.application_id or "",
            event.field_name,
            event.old_value,
            event.new_value,
            event.reason,
            event.tenant_schema,
        )
    )


def hash_row(event: "AuditEvent", prev_hash: str = "") -> str:
    """Compute the SHA-256 hash for *event* given the previous row's hash.

    ``hash_row(event) = sha256(prev_hash + canonical(event))``
    """
    payload = (prev_hash + _event_canonical(event)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def verify_chain(events: list["AuditEvent"], hashes: list[str]) -> bool:
    """Verify that *hashes* form a valid chain over *events*.

    Both lists must be in chronological order (oldest first) and have the
    same length.  The first element of *hashes* is the chain hash for the
    first event (whose ``prev_hash`` is the empty string).

    Returns ``True`` when every hash recomputes correctly; ``False`` on the
    first mismatch or length disagreement.
    """
    if len(events) != len(hashes):
        return False

    prev = ""
    for event, expected in zip(events, hashes):
        computed = hash_row(event, prev)
        if computed != expected:
            return False
        prev = expected
    return True
